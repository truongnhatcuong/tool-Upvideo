import os
import sys
import time
import random
from urllib.parse import urlsplit, urlunsplit
from typing import List, Optional, Callable


def normalize_url(url: str) -> str:
    """Loại bỏ query parameters & anchor hash để lấy URL gốc sạch."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def load_netscape_cookies(cookies_path: str) -> list:
    """Đọc file cookies.txt chuẩn định dạng Netscape để nạp vào Playwright."""
    cookies = []
    if not os.path.exists(cookies_path):
        return cookies

    with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expiration, name, value = parts[:7]
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "secure": secure.upper() == "TRUE",
                }
                try:
                    exp = int(expiration)
                    if exp > 0:
                        cookie["expires"] = exp
                except ValueError:
                    pass
                cookies.append(cookie)
    return cookies


def scroll_and_collect(
    page,
    limit: int = 0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """
    Cuộn trang liên tục để thu thập toàn bộ link video TikTok.
    """
    print(f"[+] Bắt đầu cuộn trang và quét TikTok...")
    video_links = []
    seen = set()
    no_change_rounds = 0
    max_no_change = 4  # Số lần cuộn không có video mới trước khi dừng

    while True:
        # Kiểm tra nếu user bấm nút dừng trên GUI
        if stop_check and stop_check():
            print("\n[!] Đã nhận tín hiệu dừng từ người dùng.")
            break

        # Quét tất cả các thẻ <a> chứa link video hoặc photo/slideshow
        raw_links = page.locator("a").evaluate_all("""
            elements => elements
                .map(a => a.href)
                .filter(href =>
                    href &&
                    href.includes('tiktok.com') &&
                    (href.includes('/video/') || href.includes('/photo/'))
                )
        """)
        current_count = len(video_links)

        for link in raw_links:
            clean_link = normalize_url(link)
            if clean_link not in seen:
                seen.add(clean_link)
                video_links.append(clean_link)

                if progress_callback:
                    progress_callback(len(video_links), limit, clean_link)

                if limit > 0 and len(video_links) >= limit:
                    break

        new_count = len(video_links)
        if new_count > current_count or current_count == 0:
            status_text = f"\r[SCAN] Đã tìm thấy: {new_count} video"
            if limit > 0:
                status_text += f"/{limit}"
            print(status_text, end="", flush=True)

        # Kiểm tra đạt giới hạn
        if limit > 0 and len(video_links) >= limit:
            print(f"\n[+] Đã đạt giới hạn yêu cầu ({limit} video). Hoàn tất quét!")
            return video_links[:limit]

        # Kiểm tra xem có lấy thêm được video mới không
        if new_count > current_count:
            no_change_rounds = 0
        else:
            no_change_rounds += 1

        if no_change_rounds >= max_no_change:
            print("\n[+] Đã cuộn đến cuối danh sách (không còn video mới).")
            break

        # Cuộn trang xuống
        page.mouse.wheel(0, 1200)
        # Thử thêm evaluate scroll để kích hoạt lazy-loading
        page.evaluate("window.scrollBy(0, 1000)")
        
        # Delay ngẫu nhiên để tránh bot detection
        sleep_time = random.uniform(1.2, 2.2)
        page.wait_for_timeout(int(sleep_time * 1000))

    return video_links if limit == 0 else video_links[:limit]


def extract_tiktok_links(
    playwright,
    url: str,
    limit: int = 0,
    headless: bool = False,
    cookies_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """
    Khởi động trình duyệt Playwright, truy cập URL và lấy danh sách link video TikTok.
    """
    url = url.strip()

    # Nếu truyền vào trực tiếp là link video đơn
    if "/video/" in url or "/photo/" in url:
        clean = normalize_url(url)
        print(f"[+] Phát hiện link video đơn: {clean}")
        if progress_callback:
            progress_callback(1, 1, clean)
        return [clean]

    print(f"[+] Khởi động trình duyệt (Headless={headless})...")
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )

    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="vi-VN",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    # Nạp cookies nếu có
    if cookies_path and os.path.exists(cookies_path):
        try:
            cookies = load_netscape_cookies(cookies_path)
            if cookies:
                context.add_cookies(cookies)
                print(f"[+] Đã nạp {len(cookies)} cookies từ {cookies_path}")
        except Exception as e:
            print(f"[!] Cảnh báo khi nạp cookies: {e}")

    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    print(f"[+] Đang truy cập TikTok: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[!] Cảnh báo khi tải trang: {e}")

    page.wait_for_timeout(3000)

    # Kiểm tra captcha hoặc chờ tải video
    print("[+] Đang chờ danh sách video hiển thị (Nếu có Captcha trên màn hình, vui lòng giải)...")
    for i in range(30):  # Chờ tối đa 60 giây
        if stop_check and stop_check():
            break

        error_btn = page.locator("button:has-text('Làm mới'), button:has-text('Refresh')")
        if error_btn.count() > 0 or page.locator("text='Đã xảy ra lỗi'").count() > 0:
            if i % 3 == 0:
                print("[!] TikTok báo lỗi tải trang, đang thử bấm làm mới...")
            try:
                error_btn.first.click(timeout=1000)
            except Exception:
                pass

        # Kiểm tra xem video đã hiện ra chưa
        video_count = page.locator("a[href*='/video/'], a[href*='/photo/']").count()
        if video_count > 0:
            print(f"[+] Đã tìm thấy {video_count} video ban đầu, bắt đầu quét sâu...")
            break

        page.wait_for_timeout(2000)

    links = scroll_and_collect(page, limit=limit, progress_callback=progress_callback, stop_check=stop_check)
    browser.close()
    return links
