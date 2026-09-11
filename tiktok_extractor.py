import os
import sys
import time
import random
import subprocess
from urllib.parse import urlsplit, urlunsplit
from typing import List
import config

def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def build_search_url(keyword: str) -> str:
    """Tạo URL tìm kiếm TikTok theo từ khoá."""
    from urllib.parse import quote
    return f"https://www.tiktok.com/search?q={quote(keyword)}"

def scroll_and_collect_detailed(page, limit: int = 0, exclude_links: set = None) -> tuple[List[str], dict]:
    exclude_links = exclude_links or set()
    print("[+] Bắt đầu cuộn trang và quét video TikTok...")
    if exclude_links:
        print(f"[!] Đã nạp {len(exclude_links)} video từ lịch sử để tự động né trùng.")

    video_links = []
    seen = set()
    skipped_old = 0
    no_change_rounds = 0
    
    # Đặt con trỏ chuột vào giữa màn hình để sự kiện lăn chuột và phím hoạt động chuẩn xác
    try:
        page.mouse.move(600, 400)
    except Exception:
        pass

    while True:
        # Thu thập toàn bộ link video hiện có trong trang
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
            if clean_link in seen:
                continue
            seen.add(clean_link)

            # Bỏ qua nếu video này đã từng quét hoặc đã từng đăng trong lịch sử
            if clean_link in exclude_links:
                skipped_old += 1
                continue

            video_links.append(clean_link)
            if limit > 0 and len(video_links) >= limit:
                break
                
        new_count = len(video_links)
        limit_str = f"/{limit}" if limit > 0 else " (quét tất cả)"
        skip_str = f" | Đã né {skipped_old} video cũ" if skipped_old > 0 else ""
        print(f"[SCAN] Đã thu thập: {new_count}{limit_str} video MỚI{skip_str}...")

        if limit > 0 and len(video_links) >= limit:
            print(f"[+] Đã đạt đủ số lượng video MỚI ({limit} video). Dừng cuộn!")
            details = {"raw_found": len(seen), "skipped_old": skipped_old, "new_found": limit}
            return video_links[:limit], details
            
        if new_count > current_count:
            no_change_rounds = 0
        else:
            no_change_rounds += 1
            
        if no_change_rounds >= 8:
            print(f"[+] Đã cuộn hết danh sách. Thu thập được {len(video_links)} video mới (đã né {skipped_old} video cũ).")
            break

        # Thực hiện cuộn trang đa phương thức để kích hoạt lazy-loading của TikTok:
        try:
            # 1. Lăn chuột
            page.mouse.wheel(0, 1500)
            # 2. Cuộn qua JavaScript
            page.evaluate("window.scrollBy(0, 1500)")
            # 3. Giả lập bấm phím PageDown
            page.keyboard.press("PageDown")

            # Nếu 2 lần chưa thấy thêm video, thử nhấp nhả cuộn nhẹ lên rồi cuộn mạnh xuống để trigger observer
            if no_change_rounds >= 2:
                page.evaluate("window.scrollBy(0, -300)")
                page.wait_for_timeout(300)
                page.evaluate("window.scrollBy(0, 1800)")
                page.keyboard.press("End")
        except Exception:
            pass

        # Chờ mạng tải thêm video mới (1.8s - 2.5s)
        wait_time = int((1.8 + random.uniform(0.2, 0.7)) * 1000)
        page.wait_for_timeout(wait_time)
        
    final_links = video_links if limit == 0 else video_links[:limit]
    details = {
        "raw_found": len(seen),
        "skipped_old": skipped_old,
        "new_found": len(final_links),
    }
    return final_links, details

def scroll_and_collect(page, limit: int = 0, exclude_links: set = None) -> List[str]:
    links, _ = scroll_and_collect_detailed(page, limit, exclude_links=exclude_links)
    return links

def is_captcha_active(page) -> bool:
    """Kiểm tra xem Captcha TikTok có thực sự ĐANG HIỂN THỊ (visible) trên màn hình hay không."""
    try:
        selectors = [
            "#captcha-verify-container-main-page:visible",
            "#captcha_slide_button:visible",
            ".secsdk-captcha-drag-icon:visible",
            ".captcha_verify_container:visible",
            "[id*='captcha-verify']:visible",
            "div[class*='captcha']:visible",
            "div[class*='verify-img']:visible",
            "div[class*='secsdk']:visible",
            "div.verify-wrap:visible",
        ]
        for s in selectors:
            try:
                if page.locator(s).count() > 0:
                    return True
            except Exception:
                pass

        # Kiểm tra văn bản tiếng Việt & tiếng Anh đặc trưng của khung Captcha
        captcha_texts = [
            "text='Kéo thanh trượt để hoàn thành câu đố'",
            "text='Drag the slider to fit the puzzle'",
            "text='Chọn 2 đối tượng có hình dạng giống nhau'",
            "text='Select 2 objects with the same shape'",
            "text='Xác minh để tiếp tục'",
            "text='Verify to continue'",
        ]
        for t in captcha_texts:
            try:
                loc = page.locator(t)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def extract_tiktok_links_detailed(playwright, url: str, limit: int = 0, exclude_links: set = None) -> tuple[List[str], dict]:
    """Quét link video TikTok và trả về kèm thông tin chẩn đoán lỗi (status, reason, raw_found, skipped_old).
    Hỗ trợ hồ sơ duyệt persistent và kiên nhẫn chờ người dùng giải Captcha xong mới bắt đầu quét."""
    if "/video/" in url:
        clean = normalize_url(url)
        is_dup = bool(exclude_links and clean in exclude_links)
        if is_dup:
            print(f"⚠️ Video này ({clean}) đã nằm trong lịch sử đã quét/đăng.")
            return [], {
                "status": "all_duplicate",
                "reason": "Video đơn này đã nằm trong lịch sử đã quét/đăng",
                "raw_found": 1,
                "skipped_old": 1,
            }
        return [clean], {"status": "success", "reason": "Video đơn hợp lệ", "raw_found": 1, "skipped_old": 0}
        
    profile_dir = getattr(config, "TIKTOK_PROFILE_DIR", os.path.join(config.BASE_DIR, "data", "tiktok_profile"))
    os.makedirs(profile_dir, exist_ok=True)

    is_mac = sys.platform == "darwin"
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        if is_mac else
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    print("[+] Mở trình duyệt TikTok (hồ sơ session data/tiktok_profile)...")
    context = playwright.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
        ],
        viewport={"width": 1280, "height": 850},
        user_agent=ua,
        locale="vi-VN",
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
    """)
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        pass
    
    print(f"[+] Đang truy cập TikTok: {url}")
    detected_issue = None
    links = []
    info = {"status": "unknown", "reason": "", "raw_found": 0, "skipped_old": 0}

    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e_goto:
            print(f"[!] Đang tải trang TikTok ({e_goto}), tiếp tục kiểm tra...")

        page.wait_for_timeout(2500)
        
        saw_captcha = False
        start_time = time.time()
        last_log_time = 0
        captcha_start_time = 0
        max_captcha_wait = 300  # Cho tối đa 5 phút để người dùng giải captcha thoải mái

        print("[+] Đang kiểm tra giao diện và nạp danh sách video...")
        while True:
            # 1. Kiểm tra tài khoản riêng tư
            if page.locator("text='Tài khoản này là riêng tư', text='This account is private'").count() > 0:
                print(f"❌ [LỖI KÊNH] Kênh TikTok này đang cài đặt Riêng Tư (Private) -> Không thể xem video: {url}")
                detected_issue = "Tài khoản riêng tư (Private) - không thể truy cập video"
                break

            # 2. Kiểm tra tài khoản không tồn tại
            if page.locator("text='Không thể tìm thấy tài khoản này', text='Couldn\\'t find this account'").count() > 0:
                print(f"❌ [LỖI KÊNH] Không tìm thấy tài khoản TikTok này (Link sai hoặc tài khoản bị khoá): {url}")
                detected_issue = "Không tìm thấy tài khoản (Link sai hoặc tài khoản bị khoá)"
                break

            # 3. Kiểm tra xem Captcha có đang hiển thị trên màn hình không
            if is_captcha_active(page):
                now = time.time()
                if not saw_captcha:
                    saw_captcha = True
                    captcha_start_time = now
                    last_log_time = now
                    print("\n" + "=" * 72)
                    print("⚠️ [PHÁT HIỆN CAPTCHA TIKTOK]: Trình duyệt đang yêu cầu giải câu đố!")
                    print("👉 Cửa sổ trình duyệt TikTok đã hiển thị trên màn hình.")
                    print("👉 Bạn hãy kéo thanh trượt / chọn hình để hoàn thành Captcha.")
                    print("⏳ Tool SẼ KIÊN NHẪN CHỜ BẠN GIẢI XONG (KHÔNG TỰ TẮT).")
                    print("   Sau khi bạn giải xong, tool mới bắt đầu quét video!")
                    print("=" * 72 + "\n")
                    try:
                        page.bring_to_front()
                        if is_mac:
                            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], capture_output=True)
                            subprocess.run(["osascript", "-e", 'tell application "Chromium" to activate'], capture_output=True)
                    except Exception:
                        pass
                else:
                    if now - last_log_time >= 8:
                        last_log_time = now
                        elapsed = int(now - captcha_start_time)
                        print(f"⏳ Đang chờ bạn kéo thanh trượt giải Captcha trên trình duyệt ({elapsed}s)...")

                if time.time() - captcha_start_time > max_captcha_wait:
                    print("❌ Đã quá thời gian chờ giải Captcha (5 phút).")
                    detected_issue = "Vướng Captcha TikTok chưa giải kịp trên trình duyệt (quá 5 phút)"
                    break

                page.wait_for_timeout(2000)
                continue

            # Nếu trước đó có Captcha và giờ Captcha đã biến mất -> Người dùng vừa giải xong!
            if saw_captcha:
                print("\n🎉 BẠN ĐÃ GIẢI CAPTCHA THÀNH CÔNG! Đang nạp danh sách video...")
                page.wait_for_timeout(4000)
                saw_captcha = False
                start_time = time.time() # Reset đồng hồ tính giờ quét sau khi giải Captcha
                
                # Nếu video chưa hiện ra, reload lại 1 lần để TikTok nạp video với cookie đã giải Captcha
                if page.locator("a[href*='/video/']").count() == 0:
                    print("[+] Tải lại trang nhẹ để TikTok cập nhật danh sách video...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(3500)
                    except Exception:
                        pass

            # 4. Kiểm tra nút 'Làm mới' nếu có lỗi mạng
            error_btn = page.locator("button:has-text('Làm mới'), button:has-text('Refresh')")
            if error_btn.count() > 0 or page.locator("text='Đã xảy ra lỗi'").count() > 0:
                try:
                    error_btn.first.click(timeout=1000)
                except Exception:
                    pass

            # 5. Kiểm tra xem video đã hiện ra chưa
            video_count = page.locator("a[href*='/video/']").count()
            if video_count > 0:
                print(f"[+] Đã tải xong giao diện ({video_count} video hiển thị), bắt đầu quét từ {url}!")
                break

            # Kiểm tra thời gian chờ tải trang bình thường (45s nếu không có Captcha)
            elapsed_load = time.time() - start_time
            if elapsed_load > 45:
                if is_captcha_active(page):
                    continue
                if page.locator("a[href*='/video/']").count() == 0:
                    detected_issue = "Không tìm thấy thẻ video nào hiển thị trên trang (Kênh trống hoặc bị chặn hiển thị)"
                break

            page.wait_for_timeout(2000)

        # Chẩn đoán nếu sau vòng lặp vẫn chưa tìm thấy video
        if not detected_issue:
            if is_captcha_active(page):
                detected_issue = "Vướng Captcha TikTok chưa giải kịp trên trình duyệt (quá 5 phút)"
            elif page.locator("a[href*='/video/']").count() == 0:
                detected_issue = "Không tìm thấy thẻ video nào hiển thị trên trang (Kênh trống hoặc bị chặn hiển thị)"

        if detected_issue:
            info = {"status": "error", "reason": detected_issue, "raw_found": 0, "skipped_old": 0}
        else:
            links, scroll_info = scroll_and_collect_detailed(page, limit, exclude_links=exclude_links)
            if len(links) == 0:
                if scroll_info["skipped_old"] > 0 and scroll_info["raw_found"] == scroll_info["skipped_old"]:
                    info = {
                        "status": "all_duplicate",
                        "reason": f"Toàn bộ {scroll_info['skipped_old']} video trên kênh đã có trong lịch sử quét/đăng",
                        "raw_found": scroll_info["raw_found"],
                        "skipped_old": scroll_info["skipped_old"],
                    }
                else:
                    info = {
                        "status": "empty",
                        "reason": "Không thu thập được video nào từ trang này",
                        "raw_found": scroll_info.get("raw_found", 0),
                        "skipped_old": scroll_info.get("skipped_old", 0),
                    }
            else:
                info = {
                    "status": "success",
                    "reason": f"Thu thập thành công {len(links)} video mới",
                    "raw_found": scroll_info.get("raw_found", len(links)),
                    "skipped_old": scroll_info.get("skipped_old", 0),
                }
    finally:
        try:
            context.close()
        except Exception:
            pass

    return links, info

def extract_tiktok_links(playwright, url: str, limit: int = 0, exclude_links: set = None) -> List[str]:
    links, _ = extract_tiktok_links_detailed(playwright, url, limit, exclude_links=exclude_links)
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
        'windowsfilenames': sys.platform.startswith('win'),
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


def open_tiktok_interactive_session():
    """Mở trình duyệt TikTok tương tác với profile persistent (data/tiktok_profile)
    để người dùng đăng nhập tài khoản hoặc giải trước Captcha mà không lo bị timeout."""
    import config
    from playwright.sync_api import sync_playwright

    profile_dir = getattr(config, "TIKTOK_PROFILE_DIR", os.path.join(config.BASE_DIR, "data", "tiktok_profile"))
    os.makedirs(profile_dir, exist_ok=True)
    is_mac = sys.platform == "darwin"
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        if is_mac else
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    print("\n" + "=" * 75)
    print("🌐 ĐANG MỞ TRÌNH DUYỆT TIKTOK ĐỂ ĐĂNG NHẬP / GIẢI TRƯỚC CAPTCHA...")
    print("👉 Bạn có thể đăng nhập tài khoản TikTok hoặc lướt kênh bình thường.")
    print("👉 Khi hoàn tất, bạn chỉ cần ĐÓNG CỬA SỔ TRÌNH DUYỆT.")
    print("💾 Mọi cookie và phiên xác minh sẽ được lưu tự động cho các lần quét sau!")
    print("=" * 75 + "\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            viewport={"width": 1280, "height": 850},
            user_agent=ua,
            locale="vi-VN",
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass

        try:
            page.bring_to_front()
            if is_mac:
                subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], capture_output=True)
                subprocess.run(["osascript", "-e", 'tell application "Chromium" to activate'], capture_output=True)
        except Exception:
            pass

        try:
            page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
        except Exception as e:
            print(f"[!] Đang tải TikTok ({e})...")

        # Giữ trình duyệt mở cho tới khi người dùng chủ động đóng cửa sổ
        try:
            page.wait_for_close(timeout=0)
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass

    print("\n✅ Đã lưu hồ sơ phiên TikTok thành công vào data/tiktok_profile!")

