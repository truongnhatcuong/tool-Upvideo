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
    return random.randint(config.MIN_DELAY_SEC, config.MAX_DELAY_SEC)


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
    """Chọn tư cách đăng (fanpage/cá nhân). Chấp nhận: tên hiển thị (vd 'Tôi'),
    ID (uuid) thẳng, hoặc nguyên link dạng https://ucircle.net/app/c/<id> (tự tách id ra)."""
    import re

    identity_input = (identity_input or "").strip()
    match = re.search(_UUID_RE_STR, identity_input)
    identity_id = match.group(0) if match else None

    if identity_id:
        candidates = [
            f'button[role="radio"][value="{identity_id}"]',
            f'button[role="radio"][data-value="{identity_id}"]',
            f'button[role="radio"][id="{identity_id}"]',
            f'button[role="radio"]:has(a[href*="{identity_id}"])',
            f'button[role="radio"][data-wavee-identity-id="{identity_id}"]',
            f'button[role="radio"][data-wavee-identity-option="{identity_id}"]',
        ]
    else:
        candidates = [f'button[role="radio"]:has-text("{identity_input}")']

    for selector in candidates:
        try:
            page.click(selector, timeout=2000)
            return
        except Exception:
            continue

    log(f"⚠️ Không tìm thấy nút chọn tư cách đăng cho '{identity_input}'.")


def upload_one_video(page, file_path: str, record: dict):
    description, hashtags = caption_from_record(record)
    sel = config.SELECTORS

    log(f"Đang đăng: {file_path}")
    page.goto(config.UPLOAD_URL)

    if "create_button" in sel:
        page.click(sel["create_button"])
        page.wait_for_timeout(500)

    if "tab_file" in sel:
        page.click(sel["tab_file"])
        page.wait_for_timeout(500)

    page.set_input_files(sel["file_input"], file_path)
    page.wait_for_timeout(1000)

    _select_identity(page, getattr(config, "IDENTITY_NAME", "Tôi"))

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


def _upload_worker(record: dict, cookies_path: str, browser_cookie: str, on_progress=None):
    """Chạy trong 1 thread riêng: tự mở Playwright context riêng (không share page giữa các thread).
    Tải video từ link về file tạm, đăng lên UCircle, rồi xoá file tạm ngay (không giữ lại gì trên máy)."""
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
                upload_one_video(page, temp_path, record)
                success = True
                break
            except PWTimeout:
                log(f"❌ Lần {attempt}: hết thời gian chờ xác nhận đăng cho {link}", on_progress)
                _dump_debug_screenshot(page, link, on_progress)
            except Exception as e:
                log(f"❌ Lần {attempt}: lỗi khi đăng {link} -> {e}", on_progress)
                _dump_debug_screenshot(page, link, on_progress)

        if not success:
            # Giữ trình duyệt mở thêm vài giây để bạn kịp xem màn hình UCircle đang dừng ở bước nào.
            page.wait_for_timeout(4000)

        browser.close()

    if os.path.exists(temp_path):
        os.remove(temp_path)

    return success


def run_uploads(threads: int = None, cookies_path: str = None, browser_cookie: str = None, on_progress=None, excel_path: str = None):
    """Đọc các record 'pending' trong Excel, đăng lên UCircle song song bằng nhiều luồng:
    mỗi video được tải về file tạm, đăng lên, rồi xoá file tạm ngay (không giữ lại gì trên máy).
    Mỗi luồng tự mở Playwright browser/context riêng (dùng chung storage_state đã login).

    excel_path: nếu truyền vào (vd người dùng tự chọn file qua GUI), dùng file đó thay vì
    config.EXCEL_PATH mặc định."""
    threads = threads or config.UPLOAD_THREADS_DEFAULT
    if excel_path:
        config.EXCEL_PATH = excel_path

    with sync_playwright() as p:
        ensure_logged_in(p)

    posted_set = load_posted_set()
    pending = [r for r in excel_store.load_all() if not is_duplicate(r["link"], posted_set)]

    if not pending:
        log("⚠️ Không còn video 'pending' nào trong Excel để đăng.", on_progress)
        return {"total": 0, "success": 0, "failed": 0}

    log(f"[+] Bắt đầu đăng {len(pending)} video lên UCircle với {threads} luồng...", on_progress)

    success_count = 0
    failed_count = 0
    lock = threading.Lock()

    def wrapped(record):
        nonlocal success_count, failed_count
        time.sleep(random.uniform(0, 2))  # tránh mọi luồng cùng bấm cùng lúc
        ok = _upload_worker(record, cookies_path, browser_cookie, on_progress)
        with lock:
            if ok:
                success_count += 1
                mark_as_posted(record["link"], posted_set)
            else:
                failed_count += 1

    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(wrapped, pending))

    log(f"[+] Hoàn tất: {success_count} thành công, {failed_count} thất bại.", on_progress)
    return {"total": len(pending), "success": success_count, "failed": failed_count}
