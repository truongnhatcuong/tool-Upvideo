import os
import sys
import time
import random
import subprocess
from urllib.parse import urlsplit, urlunsplit
from typing import List

def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))

def scroll_and_collect(page, limit: int = 0) -> List[str]:
    print(f"[+] Bắt đầu cuộn trang và quét TikTok...")
    video_links = []
    seen = set()
    no_change_rounds = 0
    
    while True:
        raw_links = page.locator("a").evaluate_all("""
            elements => elements
                .map(a => a.href)
                .filter(href =>
                    href &&
                    href.includes('tiktok.com') &&
                    href.includes('/video/')
                )
        """)
        current_count = len(video_links)
        
        for link in raw_links:
            clean_link = normalize_url(link)
            if clean_link not in seen:
                seen.add(clean_link)
                video_links.append(clean_link)
                if limit > 0 and len(video_links) >= limit:
                    break
                
        new_count = len(video_links)
        if new_count > current_count or current_count == 0:
            status_text = f"\r[SCAN] Đã tìm thấy: {new_count} video"
            if limit > 0:
                status_text += f"/{limit}"
            print(status_text, end="", flush=True)
            
        if limit > 0 and len(video_links) >= limit:
            print(f"\n[+] Đã đạt giới hạn LIMIT ({limit} video). Dừng cuộn!")
            return video_links[:limit]
            
        if new_count > current_count:
            no_change_rounds = 0
        else:
            no_change_rounds += 1
            
        if no_change_rounds >= 3:
            print("\n[+] Không phát hiện thêm video mới. Đã cuộn hết danh sách.")
            break
            
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(int((1.5 + random.uniform(-0.5, 1.0)) * 1000))
        
    return video_links if limit == 0 else video_links[:limit]

def extract_tiktok_links(playwright, url: str, limit: int = 0) -> List[str]:
    if "/video/" in url:
        return [normalize_url(url)]
        
    print("[+] Khởi động trình duyệt TikTok (hiển thị để xử lý Captcha nếu có)...")
    browser = playwright.chromium.launch(headless=False, args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox"
    ])
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="vi-VN",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    print(f"[+] Đang truy cập TikTok: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    
    # Kiểm tra captcha hoặc chờ tải video
    print("[+] Đang chờ giao diện tải danh sách video (Nếu có Captcha, vui lòng giải)...")
    for i in range(45): # Chờ tối đa 90 giây
        error_btn = page.locator("button:has-text('Làm mới'), button:has-text('Refresh')")
        if error_btn.count() > 0 or page.locator("text='Đã xảy ra lỗi'").count() > 0:
            if i % 3 == 0:
                print("[!] TikTok báo lỗi tải trang, đang thử tự động làm mới...")
            try:
                error_btn.first.click(timeout=1000)
            except:
                pass
                
        # Kiểm tra xem video đã hiện ra chưa
        video_count = page.locator("a[href*='/video/']").count()
        if video_count > 0:
            print("[+] Đã tải xong giao diện, bắt đầu quét video!")
            break
            
        page.wait_for_timeout(2000)
        
    links = scroll_and_collect(page, limit)
    browser.close()
    return links

def download_single_video(link: str, output_path: str, cookies_path: str = None, browser_cookie: str = None) -> bool:
    import yt_dlp
    
    if os.path.exists(output_path):
        os.remove(output_path)
        
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'windowsfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
    }
    
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif browser_cookie:
        ydl_opts['cookiesfrombrowser'] = (browser_cookie,)
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(link, download=False)
            formats = info.get('formats') or [info]
            has_video = any(f.get('vcodec') not in (None, 'none') for f in formats)
            if not has_video:
                print(f"[SKIP] Bỏ qua vì là ảnh/slideshow (không có video): {link}")
                return False

            print(f"[+] Đang tải: {link}")
            ydl.download([link])
            if os.path.exists(output_path):
                return True
        except Exception as e:
            print(f"[ERROR] Lỗi khi tải video: {e}")

    return False
