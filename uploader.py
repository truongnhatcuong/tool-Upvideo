import os
import random
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
import excel_store
import identity_manager
from dedupe import load_posted_set, is_duplicate, mark_as_posted
from caption import caption_from_record
from tiktok_extractor import download_single_video

_log_lock = threading.Lock()


class UCircleQuotaExceeded(RuntimeError):
    """UCircle account has no remaining video minutes; further uploads must stop."""


def _quota_message(page):
    """Return UCircle's quota warning text when the upload-capacity screen is visible."""
    try:
        body_text = page.locator("body").inner_text(timeout=1500)
    except Exception:
        return None

    normalized = " ".join((body_text or "").split())
    quota_markers = (
        "Đã hết dung lượng video",
        "chưa đăng thêm được",
        "Xoá bớt một video cũ",
        "Xóa bớt một video cũ",
    )
    if any(marker in normalized for marker in quota_markers):
        return normalized[:500]
    return None


def log(msg: str, on_progress=None):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    with _log_lock:
        print(line)
        os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
        with open(config.LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    if on_progress:
        on_progress(line)


def random_delay_sec():
    min_d = getattr(config, "MIN_DELAY_SEC", 60)
    max_d = getattr(config, "MAX_DELAY_SEC", 70)
    if min_d > max_d:
        min_d, max_d = max_d, min_d
    return random.randint(min_d, max_d)


def ensure_logged_in(playwright):
    """Nếu chưa có session -> mở trình duyệt cho user login tay 1 lần."""
    os.makedirs(os.path.dirname(config.STORAGE_STATE_PATH), exist_ok=True)

    if os.path.exists(config.STORAGE_STATE_PATH):
        return

    log("Chưa có session — mở trình duyệt để bạn đăng nhập tay lần đầu...")
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(permissions=['camera', 'microphone', 'geolocation'])
    page = context.new_page()
    page.goto(config.LOGIN_URL)

    input("👉 Đăng nhập xong trong cửa sổ trình duyệt thì quay lại đây, nhấn Enter... ")

    context.storage_state(path=config.STORAGE_STATE_PATH)
    log(f"✅ Đã lưu session vào {config.STORAGE_STATE_PATH}")
    browser.close()


_UUID_RE_STR = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def _select_identity(page, identity_input: str) -> bool:
    """Chọn chính xác tư cách đăng (Kênh/Fanpage hoặc Trang cá nhân).
    Dựa trên cấu trúc DOM thực tế của UCircle:
      - Container: div[data-wavee-identity-selector="true"]
      - Option: button[data-wavee-identity-option="..."]
      - Search: input[data-wavee-identity-search="true"]
    Đảm bảo: tìm đúng ID/UUID, click nhịp nhàng, kiểm tra xác nhận aria-checked="true"
    hoặc data-wavee-identity-selected="{target_id}"."""
    import re
    import identity_manager

    identity_input = (identity_input or "").strip()
    if not identity_input:
        return True

    info = identity_manager.resolve_identity_info(identity_input)
    target_id = info.get("id") or identity_input
    target_name = info.get("name") or identity_input

    # 1. Chờ khung chọn tư cách đăng xuất hiện (tối đa 15s)
    try:
        page.wait_for_selector('div[data-wavee-identity-selector="true"]', timeout=15000)
    except Exception:
        log("⚠️ Đang chờ hiển thị danh sách tư cách đăng...")

    is_me = str(target_id).lower() in ("me", "tôi", "toi")

    if is_me:
        target_selector = 'button[data-wavee-identity-option="me"]'
        uuid_str = "me"
    else:
        match = re.search(_UUID_RE_STR, str(target_id))
        uuid_str = match.group(0) if match else str(target_id)
        target_selector = f'button[data-wavee-identity-option="{uuid_str}"]'

    # Thử tìm trực tiếp nút option theo selector chuẩn
    btn = page.query_selector(target_selector)

    # Nếu danh sách dài có nhiều Circle, dùng ô tìm kiếm để lọc chính xác Circle đó
    if not btn and not is_me:
        search_input = page.query_selector('input[data-wavee-identity-search="true"]')
        if search_input:
            try:
                search_input.click()
                search_input.fill("")
                # Gõ tên kênh từ từ để UCircle lọc ra đúng kênh
                search_term = target_name[:15] if target_name else uuid_str[:8]
                search_input.type(search_term, delay=60)
                page.wait_for_timeout(800)
                btn = page.query_selector(target_selector)
                if not btn and target_name:
                    btn = page.query_selector(f'button[role="radio"]:has-text("{target_name}")')
            except Exception as e_search:
                log(f"⚠️ Thử tìm kiếm Circle: {e_search}")

    # Nếu vẫn chưa thấy, tìm theo text tên kênh
    if not btn:
        btn = page.query_selector(f'button[role="radio"]:has-text("{target_name}")')

    # Nếu vẫn chưa thấy, cuộn nhẹ vùng danh sách để tìm
    if not btn and not is_me:
        list_container = page.query_selector('div[data-wavee-identity-list="true"]')
        if list_container:
            for _ in range(6):
                list_container.evaluate('el => el.scrollTop += 250')
                page.wait_for_timeout(400)
                btn = page.query_selector(target_selector)
                if btn:
                    break

    if not btn:
        log(f"❌ KHÔNG TÌM THẤY Kênh UCircle: '{target_name}' [ID: {target_id}].")
        return False

    # Thực hiện CLICK với tốc độ vừa phải và KIỂM TRA XÁC NHẬN
    try:
        btn.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        btn.click()
        page.wait_for_timeout(800)

        # Xác minh xem Circle đã được UCircle chọn thành công chưa
        is_checked = btn.get_attribute("aria-checked") == "true"
        container = page.query_selector('div[data-wavee-identity-selector="true"]')
        selected_attr = container.get_attribute("data-wavee-identity-selected") if container else ""

        if not is_checked and selected_attr != uuid_str:
            # Click lại nếu web chưa nhận
            log("⏳ Đang xác nhận lại lựa chọn Kênh...")
            btn.click()
            page.wait_for_timeout(800)

        log(f"✅ Đã chọn CHÍNH XÁC Kênh UCircle: {target_name} [ID: {uuid_str}]")
        return True
    except Exception as e:
        log(f"❌ Lỗi khi chọn Kênh {target_name}: {e}")
        return False


def _set_crosspost(page, enable: bool = True):
    """Bật hoặc tắt tùy chọn 'Lên bảng tin' (Crosspost to newsfeed)."""
    sel_btn = config.SELECTORS.get("crosspost_button", 'button[data-wavee-upload-crosspost]')
    try:
        btn = page.query_selector(sel_btn)
        if not btn:
            btn = page.query_selector('button[role="switch"]:has-text("Lên bảng tin")')

        if btn:
            try:
                btn.scroll_into_view_if_needed()
            except Exception:
                pass
            crosspost_val = btn.get_attribute("data-wavee-upload-crosspost")
            aria_checked = btn.get_attribute("aria-checked")
            is_on = (crosspost_val == "on") or (aria_checked == "true")

            if enable and not is_on:
                btn.click()
                log("📣 Đã BẬT nút 'Lên bảng tin'")
                page.wait_for_timeout(400)
            elif not enable and is_on:
                btn.click()
                log("🔕 Đã TẮT nút 'Lên bảng tin'")
                page.wait_for_timeout(400)
    except Exception as e:
        log(f"⚠️ Thao tác nút 'Lên bảng tin': {e}")


def upload_one_video(page, file_path: str, record: dict, identity: str = None):
    description, hashtags = caption_from_record(record)
    sel = config.SELECTORS

    target_identity = identity or record.get("target_circle") or getattr(config, "IDENTITY_NAME", "me")
    circle_name = identity_manager.get_identity_name(target_identity)
    title = record.get("title") or record.get("link") or os.path.basename(file_path)
    log(f"📤 Đang đăng: \"{title[:60]}\" -> Circle: 🏷️ [{circle_name}]")
    page.goto(config.UPLOAD_URL)
    page.wait_for_timeout(1500)  # Tốc độ vừa phải: chờ trang nạp hoàn toàn

    if "create_button" in sel:
        page.click(sel["create_button"])
        page.wait_for_timeout(800)

    if "tab_file" in sel:
        page.click(sel["tab_file"])
        page.wait_for_timeout(800)

    # Nạp video và chờ UCircle render form đầy đủ
    page.set_input_files(sel["file_input"], file_path)
    page.wait_for_timeout(2000)  # Chờ 2 giây để video được nhận và hiển thị khung chọn Circle

    # Kiểm tra xem UCircle có cảnh báo tệp vượt quá 200 MB không
    err_loc = page.locator("text='Tệp vượt quá 200 MB', text*='vượt quá 200', text*='chọn video nhẹ hơn'")
    if err_loc.count() > 0:
        err_msg = err_loc.first.inner_text()
        raise ValueError(f"UCircle từ chối file (> 200MB): {err_msg}")

    # Chọn đúng Circle cho video này
    ok_id = _select_identity(page, target_identity)
    if not ok_id:
        page.wait_for_timeout(1500)
        _select_identity(page, target_identity)

    page.wait_for_timeout(800)

    # Điền mô tả
    page.fill(sel["description_box"], description)
    page.wait_for_timeout(600)

    # Thêm hashtag nhịp nhàng (delay 50ms mỗi ký tự để không bị nuốt chữ hay sót tag)
    if "hashtag_add_button" in sel:
        tags = hashtags.split()
        for tag in tags:
            try:
                page.click(sel["hashtag_add_button"])
                page.wait_for_timeout(300)
                page.keyboard.type(tag, delay=50)
                page.keyboard.press("Enter")
                page.wait_for_timeout(400)
            except Exception as e:
                log(f"⚠️ Lỗi khi thêm hashtag {tag}: {e}")

    # Xử lý nút Lên bảng tin
    crosspost_flag = getattr(config, "CROSSPOST_TO_FEED", True)
    _set_crosspost(page, crosspost_flag)
    page.wait_for_timeout(1000)

    # Bấm nút Đăng
    log(f"🚀 Bấm Đăng lên Circle 🏷️ [{circle_name}]...")
    page.click(sel["submit_button"])
    page.wait_for_timeout(800)

    quota_error = _quota_message(page)
    if quota_error:
        raise UCircleQuotaExceeded(quota_error)

    # Chờ xác nhận thành công hoặc phát hiện bảng lỗi của UCircle
    start_wait = time.time()
    success_found = False
    error_found = None
    last_pct = ""
    last_pct_time = time.time()

    while time.time() - start_wait < 90:
        if page.query_selector(sel["success_indicator"]):
            success_found = True
            break

        # Đây là lỗi cấp tài khoản, không phải lỗi video. Phát hiện ngay để
        # không chờ đủ 90 giây rồi thử lần lượt toàn bộ danh sách.
        quota_error = _quota_message(page)
        if quota_error:
            raise UCircleQuotaExceeded(quota_error)

        # 1. Kiểm tra nếu UCircle hiện bảng lỗi Ingest Stream (UCIRCLE_WAVEE_INGEST_STREAM_ALREADY_ATTACHED)
        err_modal = page.query_selector("text='Tải lên không thành công', text*='INGEST_STREAM', text*='ALREADY_ATTACHED'")
        if err_modal:
            retry_btn = page.query_selector('button:has-text("Thử lại"), button:has-text("Thử Lại")')
            if retry_btn:
                log("⚠️ Phát hiện bảng lỗi Ingest Stream của UCircle. Đang tự động bấm 'Thử lại' sau 3s...")
                time.sleep(3)
                try:
                    retry_btn.click()
                    page.wait_for_timeout(3000)
                    if page.query_selector(sel["success_indicator"]):
                        success_found = True
                        break
                except Exception:
                    pass
            error_found = "UCIRCLE_WAVEE_INGEST_STREAM_ALREADY_ATTACHED"
            break

        # 2. Theo dõi tiến trình tải lên (Đang tải lên... X%)
        try:
            pct_elem = page.query_selector("text*='%'")
            if pct_elem:
                pct_text = pct_elem.inner_text().strip()
                if pct_text and pct_text != last_pct:
                    last_pct = pct_text
                    last_pct_time = time.time()
                elif time.time() - last_pct_time > 35:
                    raise PWTimeout(f"Tiến trình tải lên bị nghẽn ở {last_pct} quá 35s")
        except PWTimeout:
            raise
        except Exception:
            pass

        page.wait_for_timeout(1000)

    if not success_found:
        if error_found:
            raise RuntimeError(f"UCircle báo lỗi tải lên: {error_found}")
        raise PWTimeout("Hết thời gian chờ xác nhận đăng (90s)")

    log(f"✅ ĐĂNG THÀNH CÔNG lên Circle 🏷️ [{circle_name}]: \"{title[:60]}\"")

    try:
        page.click(sel["success_indicator"])
        page.wait_for_timeout(1000)
    except Exception:
        pass


def _dump_debug_screenshot(page, link: str, on_progress=None):
    """Chụp lại màn hình UCircle lúc lỗi để xem đang dừng ở bước nào (đăng nhập/chọn file/điền caption/...)."""
    try:
        os.makedirs("data/debug", exist_ok=True)
        safe_name = f"data/debug/{abs(hash(link))}.png"
        page.screenshot(path=safe_name)
        log(f"🖼️ Đã lưu ảnh chụp màn hình lỗi: {safe_name} (URL hiện tại: {page.url})", on_progress)
    except Exception:
        pass


# Khóa Mutex đồng bộ hóa tải lên UCircle:
# Đảm bảo tại một thời điểm chỉ duy nhất 1 video tải lên server UCircle!
# Loại trừ 100% xung đột UCIRCLE_WAVEE_INGEST_STREAM_ALREADY_ATTACHED và dồn 100% băng thông mạng cho từng video.
_ucircle_upload_lock = threading.Lock()


def _upload_worker(record: dict, target_identity: str, cookies_path: str, browser_cookie: str, on_progress=None):
    """Chạy trong 1 thread riêng:
    1. Tải video từ TikTok về file tạm (có thể tải song song).
    2. Chiếm khóa Mutex để mở Chromium sạch và đẩy video lên UCircle độc quyền (tránh nghẽn băng thông và đụng độ stream).
    3. Xoá file tạm và nhường khóa cho luồng tiếp theo."""
    link = record["link"]
    title = (record.get("title") or record.get("caption") or link)[:50]

    # 1. Kiểm tra thời lượng nếu record có sẵn trong Excel
    dur = int(record.get("duration") or 0)
    max_dur = getattr(config, "MAX_DURATION_SEC", 180)
    if dur and dur > max_dur:
        log(f"⚠️ [BỎ QUA VIDEO QUÁ DÀI]: Video dài {dur}s ({dur//60}p > tối đa {max_dur}s) -> Bỏ qua: {link}", on_progress)
        mark_as_posted(link, load_posted_set())
        return False

    os.makedirs(config.VIDEO_FOLDER, exist_ok=True)
    temp_path = os.path.join(config.VIDEO_FOLDER, f"tmp_{abs(hash(link))}.mp4")

    ok_download = download_single_video(link, temp_path, cookies_path, browser_cookie)
    if not ok_download:
        log(f"❌ Không tải được video (bị bóp băng thông hoặc lỗi TikTok): {link}", on_progress)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False

    # 2. KIỂM TRA DUNG LƯỢNG TỆP VIDEO: UCircle giới hạn tối đa 200 MB!
    if os.path.exists(temp_path):
        size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        max_size = getattr(config, "MAX_FILE_SIZE_MB", 195)
        if size_mb > max_size:
            log(f"⚠️ [BỎ QUA TỆP > 200 MB]: Tệp video nặng {size_mb:.1f} MB (vượt ngưỡng 200 MB của UCircle).", on_progress)
            log(f"   👉 Tự động bỏ qua video: \"{title}\"", on_progress)
            try:
                os.remove(temp_path)
            except Exception:
                pass
            mark_as_posted(link, load_posted_set())
            return False

    success = False
    with _ucircle_upload_lock:
        if getattr(config, "UPLOAD_QUOTA_EXHAUSTED", False):
            log(f"⏹️ Bỏ qua tải lên vì tài khoản UCircle đã hết dung lượng video: {link}", on_progress)
            try:
                os.remove(temp_path)
            except Exception:
                pass
            return False
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=config.HEADLESS, slow_mo=getattr(config, "SLOW_MO_MS", 0))
                context = browser.new_context(
                    storage_state=config.STORAGE_STATE_PATH,
                    permissions=['camera', 'microphone', 'geolocation']
                )
                page = context.new_page()
                try:
                    upload_one_video(page, temp_path, record, identity=target_identity)
                    success = True
                except UCircleQuotaExceeded as qe:
                    config.UPLOAD_QUOTA_EXHAUSTED = True
                    config.STOP_REQUESTED = True
                    log("🛑 [HẾT DUNG LƯỢNG UCIRCLE] Tài khoản đã dùng hết số phút video cho phép.", on_progress)
                    log("   Tool đã dừng toàn bộ lượt đăng; các video chưa chạy vẫn được giữ nguyên để đăng sau khi giải phóng/mua thêm dung lượng.", on_progress)
                    log(f"   Chi tiết UCircle: {qe}", on_progress)
                    _dump_debug_screenshot(page, link, on_progress)
                except ValueError as ve:
                    err_str = str(ve)
                    if "200" in err_str or "nhẹ hơn" in err_str:
                        log(f"⚠️ [UCIRCLE TỪ CHỐI TỆP]: {err_str}", on_progress)
                        log(f"   👉 Đánh dấu bỏ qua video này: {link}", on_progress)
                        mark_as_posted(link, load_posted_set())
                    else:
                        log(f"❌ Lỗi khi đăng {link} (kênh [{target_identity}]) -> {ve}", on_progress)
                        _dump_debug_screenshot(page, link, on_progress)
                except PWTimeout as te:
                    log(f"❌ Hết thời gian chờ đăng cho {link} (kênh [{target_identity}]) -> {te}", on_progress)
                    _dump_debug_screenshot(page, link, on_progress)
                except Exception as e:
                    log(f"❌ Lỗi khi đăng {link} (kênh [{target_identity}]) -> {e}", on_progress)
                    _dump_debug_screenshot(page, link, on_progress)
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass
            if success:
                # Đợi 2s để server UCircle hoàn tất đóng kết nối stream trước khi luồng kế tiếp nhảy vào
                time.sleep(2)
        except Exception as e_pw:
            log(f"❌ Lỗi khởi chạy trình duyệt: {e_pw}", on_progress)

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return success


def run_uploads(
    threads: int = None,
    cookies_path: str = None,
    browser_cookie: str = None,
    on_progress=None,
    excel_path: str = None,
    identities: list = None,
    distribution_mode: str = None,
):
    """Đọc các record 'pending' trong Excel, đăng lên 1 hoặc NHIỀU kênh UCircle song song bằng nhiều luồng:
    mỗi video được tải về file tạm, đăng lên, rồi xoá file tạm ngay (không giữ lại gì trên máy).
    
    identities: danh sách ID/UUID kênh được chọn đăng.
    distribution_mode: 'round_robin' (xoay vòng chia đều) hoặc 'all' (đăng mỗi video lên tất cả các kênh đã chọn).
    excel_path: nếu truyền vào, dùng file đó thay vì config.EXCEL_PATH mặc định."""
    threads = threads or config.UPLOAD_THREADS_DEFAULT
    # Mỗi phiên chạy mới được phép kiểm tra lại dung lượng tài khoản.
    config.UPLOAD_QUOTA_EXHAUSTED = False
    if excel_path:
        config.EXCEL_PATH = excel_path

    target_identities = identities or getattr(config, "SELECTED_IDENTITIES", [getattr(config, "IDENTITY_NAME", "me")])
    if not target_identities:
        target_identities = ["me"]

    mode = distribution_mode or getattr(config, "DISTRIBUTION_MODE", "round_robin")

    with sync_playwright() as p:
        ensure_logged_in(p)

    posted_set = load_posted_set()
    pending = [r for r in excel_store.load_all() if not is_duplicate(r["link"], posted_set)]

    if not pending:
        log("⚠️ Không còn video 'pending' nào trong Excel để đăng.", on_progress)
        return {"total": 0, "success": 0, "failed": 0}

    # Kiểm tra xem các record có target_circle riêng không (Chế độ 1 TikTok -> 1 UCircle)
    has_individual_targets = any(bool(str(r.get("target_circle", "")).strip()) for r in pending)

    # Chia video theo từng Đợt (Round): trong mỗi đợt, tất cả các Circle đăng ĐỒNG THỜI
    rounds = []

    is_mode_all = (mode == "all")

    if is_mode_all:
        # Người dùng chủ động chọn "ĐĂNG TẤT CẢ": Mỗi video sẽ đăng lên TOÀN BỘ các kênh đã tích chọn
        log(f"\n[+] 📢 Chế độ: ĐĂNG TẤT CẢ ({len(pending)} video x {len(target_identities)} kênh đã chọn).", on_progress)
        total_tasks = len(pending) * len(target_identities)
        circle_stats = {}
        for id_val in target_identities:
            circle_stats[id_val] = {
                "id": id_val,
                "name": identity_manager.get_identity_name(id_val),
                "total": len(pending),
                "success": 0,
                "failed": 0,
            }

        success_count = 0
        failed_count = 0
        lock = threading.Lock()

        def upload_mode_all_task(item):
            nonlocal success_count, failed_count
            rec, cid = item
            c_name = identity_manager.get_identity_name(cid)
            link = rec["link"]
            title_short = (rec.get("title") or rec.get("caption") or link)[:45]

            time.sleep(random.uniform(0.3, 1.2))
            ok = _upload_worker(rec, cid, cookies_path, browser_cookie, on_progress)
            if not ok and not getattr(config, "STOP_REQUESTED", False):
                if not is_duplicate(link, load_posted_set()):
                    log(f"   ⚠️ [THỬ LẠI LẦN 2] Đang thử đăng lại video cho Circle 🏷️ [{c_name}]: \"{title_short}\"...", on_progress)
                    time.sleep(3)
                    if not getattr(config, "STOP_REQUESTED", False):
                        ok = _upload_worker(rec, cid, cookies_path, browser_cookie, on_progress)

            with lock:
                if ok:
                    success_count += 1
                    circle_stats[cid]["success"] += 1
                    s_curr = circle_stats[cid]["success"]
                    t_curr = circle_stats[cid]["total"]
                    log(f"   🎉 [THÀNH CÔNG] Đã đăng vào Circle 🏷️ [{c_name}]: \"{title_short}\" ({s_curr}/{t_curr} video)", on_progress)
                else:
                    failed_count += 1
                    circle_stats[cid]["failed"] += 1
                    log(f"   ❌ [THẤT BẠI] Lỗi khi đăng vào Circle 🏷️ [{c_name}]: {link}", on_progress)
            return ok

        for v_idx, rec in enumerate(pending, 1):
            if getattr(config, "STOP_REQUESTED", False):
                log("\n🛑 [DỪNG TIẾN TRÌNH] Đã nhận lệnh dừng từ người dùng. Ngừng đăng các đợt tiếp theo!", on_progress)
                break

            batch = [(rec, cid) for cid in target_identities]
            concurrency = max(1, min(len(batch), threads))
            v_title = (rec.get("title") or rec.get("link") or "")[:50]
            log("\n" + "=" * 75, on_progress)
            log(f"🚀 [ĐỢT #{v_idx}/{len(pending)}] ĐĂNG VIDEO '{v_title}' LÊN {len(batch)} CIRCLE:", on_progress)
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                list(pool.map(upload_mode_all_task, batch))

            mark_as_posted(rec["link"], posted_set)

            if v_idx < len(pending):
                if getattr(config, "STOP_REQUESTED", False):
                    break
                delay = random_delay_sec()
                log(f"\n⏳ Tạm dừng nghỉ {delay}s trước khi đăng video tiếp theo...", on_progress)
                end_time = time.time() + delay
                while time.time() < end_time:
                    if getattr(config, "STOP_REQUESTED", False):
                        log("🛑 [DỪNG TIẾN TRÌNH] Đã dừng ngay trong lúc chờ delay!", on_progress)
                        break
                    time.sleep(1)

    else:
        # Chế độ mặc định và chuyên sâu: 1 TikTok -> 1 UCircle (hoặc Xoay vòng)
        from collections import defaultdict
        circle_queues = defaultdict(list)

        if has_individual_targets:
            log(f"\n[+] 🎯 Chế độ: 1 TIKTOK -> 1 UCIRCLE (Mỗi video thuộc đúng Circle đã chọn).", on_progress)
            for r in pending:
                custom_id = str(r.get("target_circle", "")).strip()
                assigned_id = custom_id if custom_id else target_identities[0]
                circle_queues[assigned_id].append(r)
        else:
            log(f"\n[+] Chế độ: XOAY VÒNG ({len(pending)} video chia đều cho {len(target_identities)} kênh).", on_progress)
            for idx, r in enumerate(pending):
                assigned_id = target_identities[idx % len(target_identities)]
                circle_queues[assigned_id].append(r)

        total_tasks = sum(len(q) for q in circle_queues.values())
        log(f"[+] Tổng cộng {total_tasks} video được phân bổ cho {len(circle_queues)} Kênh UCircle.", on_progress)

        circle_stats = {}
        for cid, q in circle_queues.items():
            circle_stats[cid] = {
                "id": cid,
                "name": identity_manager.get_identity_name(cid),
                "total": len(q),
                "success": 0,
                "failed": 0,
            }

        queue_lock = threading.Lock()
        lock = threading.Lock()
        success_count = 0
        failed_count = 0

        def circle_round_worker(cid):
            """Xử lý trong 1 đợt cho Circle cid:
            Cố gắng đăng thành công 1 video cho Circle này.
            Nếu video lỗi -> thử lại video đó.
            Nếu vẫn lỗi -> lấy video tiếp theo của Circle đó để đăng bù ngay trong đợt này!"""
            nonlocal success_count, failed_count
            circle_label = identity_manager.get_identity_name(cid)

            while True:
                if getattr(config, "STOP_REQUESTED", False):
                    log(f"🛑 [DỪNG TIẾN TRÌNH] Bỏ qua tác vụ đăng của Circle 🏷️ [{circle_label}].", on_progress)
                    return False

                with queue_lock:
                    if not circle_queues[cid]:
                        return False  # Hết video trong hàng đợi của Circle này
                    record = circle_queues[cid].pop(0)

                link = record["link"]
                title_short = (record.get("title") or record.get("caption") or link)[:45]

                # 1. Thử đăng lần 1
                time.sleep(random.uniform(0.3, 1.2))
                ok = _upload_worker(record, cid, cookies_path, browser_cookie, on_progress)

                # 2. Nếu lỗi và chưa có lệnh dừng: kiểm tra xem có thử lại được không
                if not ok and not getattr(config, "STOP_REQUESTED", False):
                    # Nếu video bị loại vĩnh viễn (do quá dài hoặc quá 200MB đã được mark_as_posted trong _upload_worker)
                    if is_duplicate(link, load_posted_set()):
                        log(f"   ⏭️ [BỎ QUA] Video này không phù hợp tiêu chuẩn UCircle: {link}", on_progress)
                    else:
                        # Lỗi tải mạng / lỗi Playwright tạm thời -> THỬ LẠI CHÍNH VIDEO ĐÓ
                        log(f"   ⚠️ [THỬ LẠI LẦN 2] Gặp lỗi khi đăng. Đang thử đăng lại video cho Circle 🏷️ [{circle_label}]: \"{title_short}\"...", on_progress)
                        time.sleep(3)
                        if getattr(config, "STOP_REQUESTED", False):
                            return False
                        ok = _upload_worker(record, cid, cookies_path, browser_cookie, on_progress)

                if ok:
                    # ĐĂNG THÀNH CÔNG!
                    with lock:
                        success_count += 1
                        circle_stats[cid]["success"] += 1
                        s_curr = circle_stats[cid]["success"]
                        t_curr = circle_stats[cid]["total"]
                        log(f"   🎉 [THÀNH CÔNG] Đã đăng vào Circle 🏷️ [{circle_label}]: \"{title_short}\" ({s_curr}/{t_curr} video)", on_progress)
                        mark_as_posted(link, posted_set, circle_name=circle_label)
                    return True  # Circle này đã hoàn thành xuất sắc 1 video trong đợt này!

                else:
                    # Video này lỗi cả 2 lần (hoặc không thể tải / bị từ chối)
                    with lock:
                        failed_count += 1
                        circle_stats[cid]["failed"] += 1
                        log(f"   ❌ [LỖI] Video {link} không đăng được cho Circle 🏷️ [{circle_label}] sau khi thử lại.", on_progress)
                        mark_as_posted(link, posted_set)  # Đánh dấu để không bị kẹt lặp lại

                    if getattr(config, "STOP_REQUESTED", False):
                        return False

                    with queue_lock:
                        rem_c = len(circle_queues[cid])

                    if rem_c > 0:
                        log(f"   🔄 [CHUYỂN TIẾP] Đang lấy video khác của Circle 🏷️ [{circle_label}] (còn {rem_c} video) để đăng bù ngay trong đợt này...", on_progress)
                        time.sleep(2)
                        # Tiếp tục vòng lặp while True để lấy video kế tiếp của chính Circle này!
                    else:
                        log(f"   ⚠️ Circle 🏷️ [{circle_label}] đã hết video dự phòng trong danh sách!", on_progress)
                        return False

        round_idx = 0
        while True:
            if getattr(config, "STOP_REQUESTED", False):
                log("\n🛑 [DỪNG TIẾN TRÌNH] Đã nhận lệnh dừng từ người dùng. Ngừng các đợt tiếp theo!", on_progress)
                break

            # Lấy danh sách các Circle còn video trong hàng đợi
            active_circles = [cid for cid, q in circle_queues.items() if len(q) > 0]
            if not active_circles:
                # Tất cả các Circle đã hết video sạch sẽ!
                break

            round_idx += 1
            log("\n" + "=" * 75, on_progress)
            log(f"🚀 [ĐỢT #{round_idx}] ĐĂNG ĐỒNG THỜI CHO {len(active_circles)} CIRCLE (Số luồng: {threads}):", on_progress)
            for cid in active_circles:
                c_name = identity_manager.get_identity_name(cid)
                next_title = (circle_queues[cid][0].get("title") or circle_queues[cid][0].get("link") or "")[:45]
                rem_q = len(circle_queues[cid])
                log(f"   • Circle 🏷️ [{c_name}] (còn {rem_q} video): {next_title}", on_progress)
            log("=" * 75, on_progress)

            concurrency = max(1, min(len(active_circles), threads))
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                list(pool.map(circle_round_worker, active_circles))

            if getattr(config, "STOP_REQUESTED", False):
                log("\n🛑 [DỪNG TIẾN TRÌNH] Đã nhận lệnh dừng. Không chạy đợt tiếp theo!", on_progress)
                break

            # Kiểm tra xem còn Circle nào còn video cho các đợt tiếp theo không
            remaining_circles = [cid for cid, q in circle_queues.items() if len(q) > 0]
            if not remaining_circles:
                log("\n🎉 Tất cả các Circle đã đăng xong toàn bộ video trong danh sách!", on_progress)
                break

            delay = random_delay_sec()
            log("\n" + "-" * 75, on_progress)
            log(f"✅ [ĐỢT #{round_idx} HOÀN TẤT] Tất cả các Circle đã hoàn thành video đợt này.", on_progress)
            log(f"⏳ Còn {len(remaining_circles)} Circle có video cho đợt tiếp theo. Tạm dừng nghỉ {delay}s (thời gian delay bạn đã cài đặt) trước khi tiếp tục...", on_progress)
            log("-" * 75 + "\n", on_progress)

            end_time = time.time() + delay
            while time.time() < end_time:
                if getattr(config, "STOP_REQUESTED", False):
                    log("🛑 [DỪNG TIẾN TRÌNH] Đã dừng ngay trong lúc chờ delay!", on_progress)
                    break
                time.sleep(1)

            if getattr(config, "STOP_REQUESTED", False):
                break

    is_stopped = getattr(config, "STOP_REQUESTED", False)

    log("\n" + "=" * 75, on_progress)
    if is_stopped:
        log("🛑 [TIẾN TRÌNH ĐÃ DỪNG LẠI THEO YÊU CẦU CỦA BẠN]", on_progress)
        log("📊 BẢNG TỔNG KẾT THEO TỪNG CIRCLE KHI DỪNG:", on_progress)
    else:
        log("🎉 TẤT CẢ CÁC ĐỢT ĐÃ HOÀN TẤT THÀNH CÔNG!", on_progress)
        log("📊 BẢNG TỔNG KẾT CHI TIẾT TỪNG CIRCLE:", on_progress)

    for cid, st in circle_stats.items():
        c_name = st["name"]
        s_count = st["success"]
        t_count = st["total"]
        f_count = st["failed"]
        r_count = len(circle_queues.get(cid, [])) if not is_mode_all else (t_count - s_count - f_count)
        if is_stopped:
            log(f"   • 🏷️ [{c_name}]: ✅ Đã đăng {s_count}/{t_count} video  |  ⏳ Còn lại {r_count} video" + (f"  |  ❌ {f_count} lỗi" if f_count > 0 else ""), on_progress)
        else:
            log(f"   • 🏷️ [{c_name}]: ✅ {s_count}/{t_count} video thành công" + (f" (❌ {f_count} lỗi)" if f_count > 0 else ""), on_progress)

    log("-" * 75, on_progress)
    log(f"📈 Kết quả tổng: {success_count}/{total_tasks} lượt đăng thành công, {failed_count} thất bại.", on_progress)
    if is_stopped:
        rem_all = sum(len(q) for q in circle_queues.values()) if not is_mode_all else (total_tasks - success_count - failed_count)
        log(f"💾 Còn {rem_all} video chưa chạy vẫn được lưu nguyên vẹn trong Excel.", on_progress)
        log("👉 Lần sau khi bấm 'Bắt đầu đăng', tool sẽ tiếp tục đăng các video còn lại!", on_progress)
    log("=" * 75 + "\n", on_progress)

    return {
        "total": total_tasks,
        "success": success_count,
        "failed": failed_count,
        "stopped": is_stopped,
        "circle_stats": circle_stats,
    }

