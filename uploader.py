import os
import random
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
import excel_store
from dedupe import load_posted_set, is_duplicate, mark_as_posted
from caption import caption_from_record
from tiktok_extractor import download_single_video

_log_lock = threading.Lock()


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


def _select_identity(page, identity_input: str):
    """Chọn tư cách đăng (fanpage/cá nhân). Chấp nhận: tên hiển thị (vd 'Tôi', 'Gái Xinh', 'xe độ chiến'),
    ID (uuid) thẳng, hoặc nguyên link dạng https://ucircle.net/app/c/<id>."""
    import re
    import identity_manager

    identity_input = (identity_input or "").strip()
    if not identity_input:
        return

    info = identity_manager.resolve_identity_info(identity_input)
    target_id = info.get("id") or identity_input
    target_name = info.get("name") or identity_input

    candidates = []
    if str(target_id).lower() in ("me", "tôi", "toi"):
        candidates.extend([
            'button[role="radio"][data-wavee-identity-option="me"]',
            'button[role="radio"]:has-text("Tôi")',
        ])
    elif re.search(_UUID_RE_STR, str(target_id)):
        match_id = re.search(_UUID_RE_STR, str(target_id)).group(0)
        candidates.extend([
            f'button[role="radio"][data-wavee-identity-option="{match_id}"]',
            f'button[role="radio"][value="{match_id}"]',
            f'button[role="radio"][data-value="{match_id}"]',
            f'button[role="radio"][id="{match_id}"]',
            f'button[role="radio"]:has(a[href*="{match_id}"])',
            f'button[role="radio"][data-wavee-identity-id="{match_id}"]',
        ])

    if target_name:
        candidates.append(f'button[role="radio"]:has-text("{target_name}")')
    if target_id and target_id != target_name:
        candidates.append(f'button[role="radio"]:has-text("{target_id}")')

    for selector in candidates:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.scroll_into_view_if_needed()
                btn.click()
                log(f"✅ Đã chọn tư cách đăng: {target_name} [{target_id}]")
                return
        except Exception:
            continue

    log(f"⚠️ Không tìm thấy nút chọn tư cách đăng cho '{identity_input}'.")


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
                page.wait_for_timeout(300)
            elif not enable and is_on:
                btn.click()
                log("🔕 Đã TẮT nút 'Lên bảng tin'")
                page.wait_for_timeout(300)
    except Exception as e:
        log(f"⚠️ Thao tác nút 'Lên bảng tin': {e}")


def upload_one_video(page, file_path: str, record: dict, identity: str = None):
    description, hashtags = caption_from_record(record)
    sel = config.SELECTORS

    target_identity = identity or record.get("target_circle") or getattr(config, "IDENTITY_NAME", "me")
    log(f"Đang đăng: {file_path} -> Kênh UCircle: [{target_identity}]")
    page.goto(config.UPLOAD_URL)

    if "create_button" in sel:
        page.click(sel["create_button"])
        page.wait_for_timeout(500)

    if "tab_file" in sel:
        page.click(sel["tab_file"])
        page.wait_for_timeout(500)

    page.set_input_files(sel["file_input"], file_path)
    page.wait_for_timeout(1000)

    _select_identity(page, target_identity)

    page.fill(sel["description_box"], description)

    if "hashtag_add_button" in sel:
        tags = hashtags.split()
        for tag in tags:
            try:
                page.click(sel["hashtag_add_button"])
                page.keyboard.type(tag, delay=0) # Gõ nhanh hết cỡ
                page.keyboard.press("Enter")
                page.wait_for_timeout(100) # Chỉ chờ 100ms để tag được nhận

            except Exception as e:
                log(f"⚠️ Lỗi khi thêm hashtag {tag}: {e}")

    # Xử lý nút Lên bảng tin
    crosspost_flag = getattr(config, "CROSSPOST_TO_FEED", True)
    _set_crosspost(page, crosspost_flag)

    page.click(sel["submit_button"])

    page.wait_for_selector(sel["success_indicator"], timeout=120_000)
    log(f"✅ Đăng thành công: {file_path}")

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


def _upload_worker(record: dict, target_identity: str, cookies_path: str, browser_cookie: str, on_progress=None):
    """Chạy trong 1 thread riêng: tự mở Playwright context riêng (không share page giữa các thread).
    Tải video từ link về file tạm, đăng lên UCircle với target_identity, rồi xoá file tạm ngay."""
    link = record["link"]
    os.makedirs(config.VIDEO_FOLDER, exist_ok=True)
    temp_path = os.path.join(config.VIDEO_FOLDER, f"tmp_{abs(hash(link))}.mp4")

    ok_download = download_single_video(link, temp_path, cookies_path, browser_cookie)
    if not ok_download:
        log(f"❌ Không tải được video: {link}", on_progress)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

    success = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS, slow_mo=getattr(config, "SLOW_MO_MS", 0))
        context = browser.new_context(
            storage_state=config.STORAGE_STATE_PATH,
            permissions=['camera', 'microphone', 'geolocation']
        )
        page = context.new_page()

        for attempt in range(1, config.MAX_RETRIES_PER_VIDEO + 1):
            try:
                upload_one_video(page, temp_path, record, identity=target_identity)
                success = True
                break
            except PWTimeout:
                log(f"❌ Lần {attempt}: hết thời gian chờ xác nhận đăng cho {link} (kênh [{target_identity}])", on_progress)
                _dump_debug_screenshot(page, link, on_progress)
            except Exception as e:
                log(f"❌ Lần {attempt}: lỗi khi đăng {link} (kênh [{target_identity}]) -> {e}", on_progress)
                _dump_debug_screenshot(page, link, on_progress)

        if not success:
            page.wait_for_timeout(4000)

        browser.close()

    if os.path.exists(temp_path):
        os.remove(temp_path)

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

    if has_individual_targets:
        # Gom video theo từng Circle
        from collections import defaultdict
        circle_queues = defaultdict(list)
        for r in pending:
            custom_id = str(r.get("target_circle", "")).strip()
            assigned_id = custom_id if custom_id else target_identities[0]
            circle_queues[assigned_id].append(r)

        max_queue_len = max(len(q) for q in circle_queues.values()) if circle_queues else 0
        log(f"\n[+] 🎯 PHÁT HIỆN CẤU HÌNH: 1 TikTok -> 1 UCircle ({len(circle_queues)} Kênh có video cần đăng).", on_progress)

        # Xếp các đợt: mỗi đợt lấy 1 video từ mỗi Circle để chạy đồng thời
        for r_idx in range(max_queue_len):
            round_batch = []
            for cid, q in circle_queues.items():
                if r_idx < len(q):
                    round_batch.append((q[r_idx], cid))
            if round_batch:
                rounds.append(round_batch)

    elif mode == "all":
        # Mỗi video đăng lên toàn bộ các kênh đã chọn đồng thời
        log(f"\n[+] Chế độ: ĐĂNG TẤT CẢ ({len(pending)} video x {len(target_identities)} kênh).", on_progress)
        for r in pending:
            round_batch = [(r, id_val) for id_val in target_identities]
            rounds.append(round_batch)

    else:  # round_robin
        log(f"\n[+] Chế độ: XOAY VÒNG ({len(pending)} video chia đều cho {len(target_identities)} kênh).", on_progress)
        step = len(target_identities)
        for i in range(0, len(pending), step):
            chunk = pending[i : i + step]
            round_batch = []
            for idx, r in enumerate(chunk):
                assigned_id = target_identities[idx % len(target_identities)]
                round_batch.append((r, assigned_id))
            if round_batch:
                rounds.append(round_batch)

    total_tasks = sum(len(b) for b in rounds)
    log(f"[+] Tổng cộng {total_tasks} lượt đăng được chia làm {len(rounds)} đợt chạy đồng thời.", on_progress)

    success_count = 0
    failed_count = 0
    lock = threading.Lock()
    task_posted_tracker = {}

    def upload_task(task_item):
        nonlocal success_count, failed_count
        record, id_val = task_item
        time.sleep(random.uniform(0.1, 1.5))  # Tránh các luồng cùng bấm cùng một millisecond
        ok = _upload_worker(record, id_val, cookies_path, browser_cookie, on_progress)
        with lock:
            if ok:
                success_count += 1
                link = record["link"]
                task_posted_tracker[link] = task_posted_tracker.get(link, 0) + 1
                needed = 1 if (has_individual_targets or mode != "all") else len(target_identities)
                if task_posted_tracker[link] >= needed:
                    mark_as_posted(link, posted_set)
            else:
                failed_count += 1
        return ok

    # THỰC THI TỪNG ĐỢT: CÁC CIRCLE CHẠY ĐỒNG THỜI TRONG ĐỢT
    for round_idx, round_batch in enumerate(rounds, 1):
        log("\n" + "=" * 75, on_progress)
        log(f"🚀 [ĐỢT #{round_idx}/{len(rounds)}] BẮT ĐẦU ĐĂNG ĐỒNG THỜI {len(round_batch)} VIDEO CHO CÁC CIRCLE:", on_progress)
        for rec, id_val in round_batch:
            log(f"   • Kênh [{id_val}]: {rec.get('link')}", on_progress)
        log("=" * 75, on_progress)

        # Số luồng trong đợt = tối thiểu bằng số circle trong đợt để chạy đồng thời
        concurrency = max(len(round_batch), threads)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(upload_task, round_batch))

        # Sau khi cả đợt đã đăng xong: kiểm tra xem có còn đợt tiếp theo không
        if round_idx < len(rounds):
            delay = random_delay_sec()
            remaining_rounds = len(rounds) - round_idx
            log("\n" + "-" * 75, on_progress)
            log(f"✅ [ĐỢT #{round_idx} HOÀN TẤT] Cả {len(round_batch)} Circle đã đăng xong video đợt này.", on_progress)
            log(f"⏳ Còn {remaining_rounds} đợt nữa. Tạm dừng nghỉ {delay}s (thời gian delay bạn đã cài đặt) trước khi tiếp tục...", on_progress)
            log("-" * 75 + "\n", on_progress)
            time.sleep(delay)

    log("\n" + "=" * 75, on_progress)
    log(f"🎉 TẤT CẢ CÁC ĐỢT ĐÃ HOÀN TẤT!", on_progress)
    log(f"📊 Kết quả: {success_count}/{total_tasks} lượt đăng thành công, {failed_count} thất bại.", on_progress)
    log("=" * 75 + "\n", on_progress)

    return {"total": total_tasks, "success": success_count, "failed": failed_count}
