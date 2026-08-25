import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import tiktok_extractor
import excel_store
import dedupe


def _fetch_metadata_staggered(link, cookies_path, browser_cookie):
    """Giãn cách nhỏ trước mỗi request để tránh nhiều luồng cùng bắn 1 lúc
    (dễ bị TikTok coi là bot -> lỗi 'Unable to extract universal data')."""
    time.sleep(random.uniform(0.3, 1.2))
    return tiktok_extractor.fetch_metadata(link, cookies_path, browser_cookie)


def quality_filter(meta: dict, min_views: int, min_likes: int, min_resolution: int) -> bool:
    if not meta:
        return False
    if meta.get("views", 0) < min_views:
        return False
    if meta.get("likes", 0) < min_likes:
        return False
    if meta.get("height", 0) < min_resolution:
        return False
    return True


def scrape_and_filter(
    playwright,
    source: str,
    is_keyword: bool = False,
    limit: int = 0,
    scrape_threads: int = None,
    min_views: int = None,
    min_likes: int = None,
    min_resolution: int = None,
    cookies_path: str = None,
    browser_cookie: str = None,
    exclude_history: bool = True,
    on_progress=None,
) -> dict:
    """Quét link TikTok (Profile hoặc Từ khoá), lấy metadata song song, lọc chất lượng,
    ghi kết quả đạt chuẩn vào Excel. Trả về {"scanned": n, "passed": n, "rejected": n}."""
    scrape_threads = scrape_threads or config.SCRAPE_THREADS_DEFAULT
    min_views = config.MIN_VIEWS if min_views is None else min_views
    min_likes = config.MIN_LIKES if min_likes is None else min_likes
    min_resolution = config.MIN_RESOLUTION_HEIGHT if min_resolution is None else min_resolution

    def log(msg):
        print(msg)
        if on_progress:
            on_progress(msg)

    exclude_links = dedupe.load_all_seen_links() if exclude_history else set()
    url = tiktok_extractor.build_search_url(source) if is_keyword else source

    log(f"[+] Đang quét link từ: {url}")
    if exclude_links:
        log(f"[!] Đã nạp {len(exclude_links)} video đã quét/đăng từ trước để tự động né trùng lặp.")

    links = tiktok_extractor.extract_tiktok_links(playwright, url, limit, exclude_links=exclude_links)
    log(f"[+] Tìm thấy {len(links)} link mới. Đang lấy metadata song song ({scrape_threads} luồng)...")

    passed_rows = []
    rejected = 0

    with ThreadPoolExecutor(max_workers=scrape_threads) as pool:
        futures = {
            pool.submit(_fetch_metadata_staggered, link, cookies_path, browser_cookie): link
            for link in links
        }
        for i, future in enumerate(as_completed(futures), 1):
            link = futures[future]
            try:
                meta = future.result()
            except Exception as e:
                log(f"[ERROR] {link}: {e}")
                meta = {}

            if quality_filter(meta, min_views, min_likes, min_resolution):
                passed_rows.append({
                    "link": meta["link"],
                    "caption": meta["caption"],
                    "hashtags": meta["hashtags"],
                    "views": meta["views"],
                    "likes": meta["likes"],
                    "resolution": f"{meta['width']}x{meta['height']}",
                })
                log(f"[{i}/{len(links)}] ✅ Đạt chất lượng: {link}")
            else:
                rejected += 1
                log(f"[{i}/{len(links)}] ⏭️ Loại (không đạt ngưỡng): {link}")

    added = excel_store.append_records(passed_rows)
    if passed_rows:
        dedupe.mark_as_scanned([r["link"] for r in passed_rows])
    log(f"[+] Đã lưu {added} video mới vào {config.EXCEL_PATH} (loại {rejected} video).")

    return {"scanned": len(links), "passed": added, "rejected": rejected}
