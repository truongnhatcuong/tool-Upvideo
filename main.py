"""
CHẠY: python main.py

Lần đầu chạy: trình duyệt sẽ mở ra trang login, bạn đăng nhập tay 1 lần,
quay lại đây gõ Enter -> tool lưu session, những lần sau tự động luôn,
không cần đăng nhập lại.

Sau khi có session, tool tự lặp: lấy video mới trong videos/ -> điền
mô tả + hashtag -> bấm đăng -> đánh dấu đã đăng -> chờ vài phút -> video kế tiếp.
"""

import os
import shutil
import random
import time
import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
from dedupe import load_posted_set, is_duplicate, mark_as_posted
from caption import generate_caption

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


def log(msg: str):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_pending_videos(posted_set: set):
    if not os.path.isdir(config.VIDEO_FOLDER):
        return []
    files = [
        os.path.join(config.VIDEO_FOLDER, f)
        for f in os.listdir(config.VIDEO_FOLDER)
        if f.lower().endswith(VIDEO_EXTS)
    ]
    return [f for f in files if not is_duplicate(f, posted_set)]


def random_delay_sec():
    return random.randint(config.MIN_DELAY_SEC, config.MAX_DELAY_SEC)


def ensure_logged_in(playwright):
    """Nếu chưa có session -> mở trình duyệt cho user login tay 1 lần."""
    os.makedirs(os.path.dirname(config.STORAGE_STATE_PATH), exist_ok=True)

    if os.path.exists(config.STORAGE_STATE_PATH):
        return  # đã có session rồi, không cần login lại

    log("Chưa có session — mở trình duyệt để bạn đăng nhập tay lần đầu...")
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(config.LOGIN_URL)

    input("👉 Đăng nhập xong trong cửa sổ trình duyệt thì quay lại đây, nhấn Enter... ")

    context.storage_state(path=config.STORAGE_STATE_PATH)
    log(f"✅ Đã lưu session vào {config.STORAGE_STATE_PATH}")
    browser.close()


def upload_one_video(page, file_path: str):
    description, hashtags = generate_caption(file_path)
    sel = config.SELECTORS

    log(f"Đang đăng: {file_path}")
    page.goto(config.UPLOAD_URL)

    # Click nút "Đăng Sóng" (+)
    if "create_button" in sel:
        page.click(sel["create_button"])
        page.wait_for_timeout(1000)

    # Click chuyển sang tab "Tải lên"
    if "tab_file" in sel:
        page.click(sel["tab_file"])
        page.wait_for_timeout(1000)

    # Bắt đầu chọn file
    page.set_input_files(sel["file_input"], file_path)
    
    # Chờ giao diện tải lên (preview) xuất hiện
    page.wait_for_timeout(2000)

    # Chọn tư cách đăng (Trang cá nhân hoặc Fanpage) bằng TÊN
    identity_name = getattr(config, "IDENTITY_NAME", "Tôi")
    # Playwright có tính năng tìm element chứa chữ (has-text) rất tiện
    identity_selector = f'button[role="radio"]:has-text("{identity_name}")'
    try:
        page.click(identity_selector, timeout=3000)
    except Exception:
        log(f"⚠️ Không tìm thấy nút chọn tư cách đăng có tên '{identity_name}'.")

    # Điền chú thích (chỉ text, không chứa hashtag)
    page.fill(sel["description_box"], description)

    # Thêm từng hashtag rời qua nút bấm
    if "hashtag_add_button" in sel:
        # Tách chuỗi "#trend #viral #fyp" thành danh sách
        tags = hashtags.split()
        for tag in tags:
            try:
                # Bấm nút "+ hashtag"
                page.click(sel["hashtag_add_button"])
                page.wait_for_timeout(300)
                # Gõ chữ hashtag (thường trình duyệt tự focus vào ô nhập sau khi bấm nút)
                page.keyboard.type(tag)
                page.wait_for_timeout(200)
                # Bấm phím Enter để chốt tag
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
            except Exception as e:
                log(f"⚠️ Lỗi khi thêm hashtag {tag}: {e}")

    # Bấm đăng
    page.click(sel["submit_button"])
    
    # Đợi nút "Đăng video khác" hiện ra (tức là đã đăng xong)
    page.wait_for_selector(sel["success_indicator"], timeout=120_000)
    log(f"✅ Đăng thành công: {file_path}")

    # Bấm nút "Đăng video khác" để giao diện quay về trạng thái sẵn sàng cho vòng lặp tiếp theo
    try:
        page.click(sel["success_indicator"])
        page.wait_for_timeout(1000)
    except Exception:
        pass


def move_to_posted(file_path: str):
    os.makedirs(config.POSTED_FOLDER, exist_ok=True)
    dest = os.path.join(config.POSTED_FOLDER, os.path.basename(file_path))
    shutil.move(file_path, dest)


def run():
    with sync_playwright() as p:
        ensure_logged_in(p)

        browser = p.chromium.launch(headless=config.HEADLESS)
        context = browser.new_context(storage_state=config.STORAGE_STATE_PATH)
        page = context.new_page()

        while True:
            posted_set = load_posted_set()
            pending = get_pending_videos(posted_set)

            if not pending:
                log("⚠️ Không còn video mới trong videos/. Hãy bổ sung thêm rồi chạy lại. Dừng.")
                break

            video = pending[0]
            success = False

            for attempt in range(1, config.MAX_RETRIES_PER_VIDEO + 1):
                try:
                    upload_one_video(page, video)
                    success = True
                    break
                except PWTimeout:
                    log(f"❌ Lần {attempt}: hết thời gian chờ xác nhận đăng thành công cho {video}")
                except Exception as e:
                    log(f"❌ Lần {attempt}: lỗi khi đăng {video} -> {e}")

            if success:
                mark_as_posted(video, posted_set)
                move_to_posted(video)
            else:
                log(f"⏭️ Bỏ qua video lỗi: {video} (không đánh dấu đã đăng, sẽ thử lại lần chạy sau)")

            delay = random_delay_sec()
            log(f"⏳ Chờ {delay // 60} phút {delay % 60} giây trước video tiếp theo...")
            time.sleep(delay)

        browser.close()


if __name__ == "__main__":
    run()
