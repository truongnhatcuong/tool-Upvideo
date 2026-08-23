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


def build_search_url(keyword: str) -> str:
    """Tạo URL tìm kiếm TikTok theo từ khoá."""
    from urllib.parse import quote
    return f"https://www.tiktok.com/search?q={quote(keyword)}"

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

def _impersonate_target():
    """Trả về target giả lập trình duyệt Chrome cho yt-dlp (cần gói curl_cffi).
    Phải truyền object ImpersonateTarget (không phải chuỗi 'chrome' thô) để tránh
    lỗi AssertionError trong yt-dlp khi gọi qua API Python. Nếu thiếu curl_cffi
    thì bỏ qua tính năng này (không impersonate) thay vì làm crash toàn bộ."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        return ImpersonateTarget.from_str('chrome')
    except Exception:
        return None


def download_single_video(link: str, output_path: str, cookies_path: str = None, browser_cookie: str = None, max_retries: int = 3) -> bool:
    import time
    import yt_dlp

    # Cấu hình yt-dlp
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'windowsfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
        }
    }
    impersonate_target = _impersonate_target()
    if impersonate_target:
        ydl_opts['impersonate'] = impersonate_target

    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif browser_cookie:
        ydl_opts['cookiesfrombrowser'] = (browser_cookie,)

    # HÀM DỰ PHÒNG TIKWM (API bên thứ 3)
    def download_via_api(url, dest):
        try:
            import requests
            resp = requests.post("https://www.tikwm.com/api/", data={"url": url}, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                play_url = data["data"].get("hdplay") or data["data"].get("play")
                if play_url:
                    vid_resp = requests.get(play_url, stream=True, timeout=30)
                    vid_resp.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in vid_resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    return True
        except Exception:
            pass
        return False

    for attempt in range(1, max_retries + 1):
        if os.path.exists(output_path):
            os.remove(output_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                if not info:
                    raise RuntimeError("extract_info trả về None")

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
            print(f"[ERROR] Lỗi yt-dlp (lần {attempt}/{max_retries}): {e}")
            print(f"[+] Thử chuyển sang hệ thống API dự phòng (TikWM)...")
            if download_via_api(link, output_path):
                print(f"[+] Tải thành công bằng API dự phòng!")
                return True

        if attempt < max_retries:
            wait = attempt * 2 + random.uniform(0, 1.5)
            time.sleep(wait)

    return False


def _extract_hashtags(text: str):
    import re
    return re.findall(r"#\w+", text or "")


def _looks_like_fake_id_tag(tag: str, video_id: str) -> bool:
    """yt-dlp đôi khi trả title/tags kiểu 'TikTok video #<id>' khi không lấy được
    caption thật -- đây KHÔNG phải hashtag thật, cần loại bỏ."""
    stripped = tag.lstrip("#")
    return stripped.isdigit() and (not video_id or stripped == video_id)


def _strip_quotes(text: str) -> str:
    """Bỏ dấu ngoặc kép/nháy bao quanh caption, vd '"Thử thách mới!"' -> 'Thử thách mới!'."""
    text = text.strip()
    pairs = [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")]
    for left, right in pairs:
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            text = text[1:-1].strip()
            break
    return text


def _split_caption_and_hashtags(description: str, video_id: str):
    """Tách phần chữ (caption thật) ra khỏi các hashtag trong description,
    tránh caption == hashtags khi video không có nội dung chữ riêng."""
    import re

    hashtags = _extract_hashtags(description)
    hashtags = [h for h in hashtags if not _looks_like_fake_id_tag(h, video_id)]

    clean_caption = description
    for h in hashtags:
        clean_caption = clean_caption.replace(h, "")
    clean_caption = re.sub(r"\s+", " ", clean_caption).strip()
    clean_caption = _strip_quotes(clean_caption)

    return clean_caption, hashtags


def fetch_metadata(link: str, cookies_path: str = None, browser_cookie: str = None, max_retries: int = 3) -> dict:
    """Lấy caption, hashtag, view/like, độ phân giải TỪ METADATA (yt-dlp), KHÔNG tải file video.
    Trả về dict rỗng {} nếu lỗi/không lấy được (để bên gọi tự loại video này).

    TikTok hay trả về trang "rút gọn" (lỗi "Unable to extract universal data for
    rehydration") khi nghi ngờ bot -- thường do bắn nhiều request song song mà
    KHÔNG có cookie đăng nhập. Vì vậy ở đây có retry + nghỉ giãn cách tăng dần,
    và nên truyền cookies_path/browser_cookie khi gọi hàm này để giảm tỉ lệ lỗi."""
    import time
    import random
    import yt_dlp

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
        }
    }
    impersonate_target = _impersonate_target()
    if impersonate_target:
        ydl_opts['impersonate'] = impersonate_target

    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif browser_cookie:
        ydl_opts['cookiesfrombrowser'] = (browser_cookie,)
    # Không chọn gì -> không dùng cookie (KHÔNG tự ép đọc cookie Chrome, vì Chrome
    # đang mở sẽ khoá file cookie khiến yt-dlp lỗi 'failed to load cookies').

    # HÀM DỰ PHÒNG TIKWM (API bên thứ 3) cho Metadata
    def fetch_via_api(url):
        try:
            import requests
            resp = requests.post("https://www.tikwm.com/api/", data={"url": url}, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                vid = data["data"]
                return {
                    'id': vid.get('id'),
                    'title': vid.get('title'),
                    'description': vid.get('title'),
                    'view_count': vid.get('play_count'),
                    'like_count': vid.get('digg_count'),
                    'uploader': vid.get('author', {}).get('unique_id'),
                    'width': 1080, # mặc định HD
                    'height': 1920
                }
        except Exception:
            pass
        return None

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
            if not info:
                info = fetch_via_api(link)
                if not info:
                    last_error = "không có dữ liệu trả về kể cả dùng API"
            
            if info:
                video_id = str(info.get('id') or '')
                # yt-dlp tự sinh title kiểu "TikTok video #<id>" khi không lấy được
                # caption thật -> KHÔNG dùng làm caption thật (chỉ dùng description thật).
                description = (info.get('description') or '').strip()
                clean_caption, hashtags = _split_caption_and_hashtags(description, video_id)

                if not hashtags:
                    tag_pool = [f"#{t}" for t in (info.get('tags') or []) if t]
                    hashtags = [h for h in tag_pool if not _looks_like_fake_id_tag(h, video_id)]

                # 3 trường hợp cần AI (luôn gen dựa theo ngữ cảnh có sẵn để đúng chủ đề):
                #  - thiếu cả caption lẫn hashtag -> gen cả 2 (dựa theo kênh/tiêu đề)
                #  - có hashtag, thiếu caption     -> gen caption (dựa theo hashtag)
                #  - có caption, thiếu hashtag     -> gen hashtag (dựa theo caption)
                import ai_caption
                title = (info.get('title') or '').strip()
                original_tags = [t for t in (info.get('tags') or []) if t]
                uploader = info.get('uploader') or info.get('channel') or ''

                context_parts = []
                if title and video_id and video_id in title and len(title) < len(video_id) + 20:
                    pass  # title kiểu "TikTok video #<id>" -> không có thông tin thật, bỏ qua
                elif title:
                    context_parts.append(title)
                if original_tags:
                    context_parts.append(" ".join(original_tags[:8]))
                if uploader:
                    context_parts.append(f"kênh: {uploader}")

                topic_context = " | ".join(context_parts) or video_id or link

                if not clean_caption and not hashtags:
                    clean_caption, hashtags_str = ai_caption.generate_caption_and_hashtags(topic_context)
                    hashtags = hashtags_str.split() if hashtags_str else []
                    if not clean_caption:
                        print(f"[SKIP] Bỏ qua vì video không có caption/hashtag và AI không sinh được: {link}")
                        return {}
                elif not clean_caption:
                    clean_caption = ai_caption.generate_caption(" ".join(hashtags))
                    if not clean_caption:
                        print(f"[SKIP] Bỏ qua vì video không có caption thật và AI không sinh được: {link}")
                        return {}
                elif not hashtags:
                    hashtags_str = ai_caption.generate_hashtags(clean_caption)
                    hashtags = hashtags_str.split() if hashtags_str else []
                    if not hashtags:
                        print(f"[SKIP] Bỏ qua vì video không có hashtag thật và AI không sinh được: {link}")
                        return {}

                return {
                    "link": link,
                    "caption": clean_caption,
                    "hashtags": " ".join(hashtags),
                    "views": int(info.get('view_count') or 0),
                    "likes": int(info.get('like_count') or 0),
                    "width": int(info.get('width') or 0),
                    "height": int(info.get('height') or 0),
                }
        except Exception as e:
            last_error = e

        if attempt < max_retries:
            wait = attempt * 2 + random.uniform(0, 1.5)  # 2-3.5s, 4-5.5s, ...
            time.sleep(wait)

    print(f"[ERROR] Lỗi khi lấy metadata {link} (đã thử {max_retries} lần): {last_error}")
    print("        -> Nếu lỗi 'Unable to extract universal data', hãy giảm số luồng quét "
          "và/hoặc chọn Cookie TikTok (đăng nhập trình duyệt) trong GUI để giảm tỉ lệ bị chặn.")
    return {}
