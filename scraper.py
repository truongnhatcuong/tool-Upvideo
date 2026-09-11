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


def _parse_sources(source, default_circle: str = "", is_keyword_default: bool = False) -> list:
    """Chuyển chuỗi hoặc danh sách nguồn thành danh sách các tuple:
    (url_or_kw, is_keyword, target_circle).
    Cú pháp hỗ trợ trên mỗi dòng:
      <link hoặc từ khoá> | <Tên hoặc ID UCircle mục tiêu>
    Ví dụ:
      https://www.tiktok.com/@xedochien | xe độ chiến
      https://www.tiktok.com/@gaixinh_vn | Gái Xinh
    Nếu không có dấu '|', sẽ sử dụng default_circle."""
    if isinstance(source, str):
        lines = [s.strip() for s in source.replace(",", "\n").splitlines() if s.strip()]
    elif isinstance(source, (list, tuple)):
        lines = [str(s).strip() for s in source if str(s).strip()]
    else:
        lines = []

    parsed = []
    for item in lines:
        target_circle = default_circle
        raw_part = item
        if "|" in item:
            parts = item.split("|", 1)
            raw_part = parts[0].strip()
            target_circle = parts[1].strip() or default_circle

        if raw_part.startswith("@"):
            parsed.append((f"https://www.tiktok.com/{raw_part}", False, target_circle))
        elif raw_part.startswith("http://") or raw_part.startswith("https://") or "tiktok.com" in raw_part:
            parsed.append((raw_part, False, target_circle))
        else:
            parsed.append((raw_part, True if is_keyword_default else False, target_circle))
    return parsed


def scrape_single_source(
    playwright,
    raw_source: str,
    target_circle: str = "",
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
    """Quét riêng biệt duy nhất 1 kênh TikTok và lưu nối tiếp kết quả vào Excel hiện có."""
    scrape_threads = scrape_threads or config.SCRAPE_THREADS_DEFAULT
    min_views = config.MIN_VIEWS if min_views is None else min_views
    min_likes = config.MIN_LIKES if min_likes is None else min_likes
    min_resolution = config.MIN_RESOLUTION_HEIGHT if min_resolution is None else min_resolution

    def log(msg):
        print(msg)
        if on_progress:
            on_progress(msg)

    exclude_links = dedupe.load_all_seen_links() if exclude_history else set()

    raw_clean = raw_source.strip()
    if raw_clean.startswith("@"):
        target_url = f"https://www.tiktok.com/{raw_clean}"
    elif raw_clean.startswith("http://") or raw_clean.startswith("https://") or "tiktok.com" in raw_clean:
        target_url = raw_clean
    elif is_keyword:
        target_url = tiktok_extractor.build_search_url(raw_clean)
    else:
        target_url = raw_clean

    target_label = target_circle if target_circle else "(Mặc định / Chưa chọn)"

    log("\n" + "=" * 75)
    log(f"🔄 [QUÉT RIÊNG KÊNH]: {raw_clean}")
    log(f"🎯 Mục tiêu đăng vào Kênh UCircle: [{target_label}]")
    log("=" * 75)

    try:
        links, info = tiktok_extractor.extract_tiktok_links_detailed(
            playwright, target_url, limit, exclude_links=exclude_links
        )
    except Exception as e:
        log(f"❌ [LỖI TRUY CẬP] Khi quét {raw_clean}: {e}")
        return {
            "source": raw_clean,
            "target_circle": target_label,
            "found": 0,
            "passed": 0,
            "rejected": 0,
            "issue": f"Lỗi ngoại lệ: {e}",
            "error": str(e)
        }

    detected_issue = info.get("reason", "") if info.get("status") != "success" else None

    if not links:
        log("\n" + "-" * 75)
        log(f"⚠️ [KẾT QUẢ]: 0 VIDEO THU THẬP TỪ KÊNH: {raw_clean}")
        log(f"👉 Lý do: {detected_issue or 'Không tìm thấy video nào'}")
        log(f"👉 Hướng dẫn: Vui lòng kiểm tra lại link, giải Captcha trên trình duyệt hoặc thử lại sau.")
        log("-" * 75 + "\n")
        return {
            "source": raw_clean,
            "target_circle": target_label,
            "found": 0,
            "passed": 0,
            "rejected": 0,
            "issue": detected_issue or "0 video thu thập được",
            "error": None
        }

    log(f"✅ Thu thập thành công {len(links)} video mới. Đang kiểm tra chất lượng metadata ({scrape_threads} luồng)...")

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
                    "target_circle": target_circle,
                })
                log(f"[{i}/{len(links)}] ✅ Đạt chất lượng [-> {target_label}]: {link}")
            else:
                rejected += 1
                log(f"[{i}/{len(links)}] ⏭️ Loại (không đạt ngưỡng): {link}")

    added = excel_store.append_records(passed_rows)
    if passed_rows:
        dedupe.mark_as_scanned([r["link"] for r in passed_rows])

    log("\n" + "=" * 75)
    log(f"🎯 KẾT QUẢ QUÉT RIÊNG: {raw_clean} ➡️ UCircle: [{target_label}]")
    log(f"   📹 Tìm thấy: {len(links)} video | Đạt chuẩn lưu vào Excel: {added} video | Bị loại: {rejected} video")
    log("=" * 75 + "\n")

    issue = None
    if added == 0:
        if len(links) > 0:
            issue = f"Thu thập được {len(links)} video nhưng không có video nào đạt ngưỡng views/likes"
        else:
            issue = detected_issue or "0 video thu thập được"

    return {
        "source": raw_clean,
        "target_circle": target_label,
        "found": len(links),
        "passed": added,
        "rejected": rejected,
        "issue": issue,
        "error": None
    }


def scrape_and_filter(
    playwright,
    source,
    is_keyword: bool = False,
    default_circle: str = "",
    limit: int = 0,
    scrape_threads: int = None,
    min_views: int = None,
    min_likes: int = None,
    min_resolution: int = None,
    cookies_path: str = None,
    browser_cookie: str = None,
    exclude_history: bool = True,
    on_progress=None,
    on_source_start=None,
    on_source_done=None,
) -> dict:
    """Quét link TikTok từ 1 hoặc NHIỀU nguồn (Kênh hoặc Từ khoá), gán UCircle mục tiêu cho từng nguồn,
    lấy metadata song song, lọc chất lượng, ghi kết quả kèm target_circle vào Excel.
    Trả về dict tổng quan chi tiết và danh sách các kênh thất bại cần quét lại."""
    scrape_threads = scrape_threads or config.SCRAPE_THREADS_DEFAULT
    min_views = config.MIN_VIEWS if min_views is None else min_views
    min_likes = config.MIN_LIKES if min_likes is None else min_likes
    min_resolution = config.MIN_RESOLUTION_HEIGHT if min_resolution is None else min_resolution

    def log(msg):
        print(msg)
        if on_progress:
            on_progress(msg)

    sources_list = _parse_sources(source, default_circle=default_circle, is_keyword_default=is_keyword)
    if not sources_list:
        log("⚠️ Không có link hoặc từ khoá TikTok nào hợp lệ để quét.")
        return {"scanned": 0, "passed": 0, "rejected": 0, "sources": 0, "failed_sources": []}

    exclude_links = dedupe.load_all_seen_links() if exclude_history else set()
    if exclude_links:
        log(f"[!] Đã nạp {len(exclude_links)} video đã quét/đăng từ trước để tự động né trùng lặp.")

    log(f"[+] Bắt đầu quét từ {len(sources_list)} nguồn TikTok (chế độ 1 TikTok = 1 UCircle)...")

    all_links = []
    seen_in_batch = set()
    link_to_circle = {}
    link_to_source = {}
    source_stats = {}

    for idx, (raw_src, is_kw, target_circle) in enumerate(sources_list, 1):
        target_url = tiktok_extractor.build_search_url(raw_src) if is_kw else raw_src
        target_label = target_circle if target_circle else "(Dùng kênh mặc định)"
        source_stats[raw_src] = {
            "idx": idx,
            "target_circle": target_label,
            "found": 0,
            "passed": 0,
            "rejected": 0,
            "issue": None,
            "error": None,
        }

        if on_source_start:
            try:
                on_source_start(idx, raw_src, target_label)
            except Exception:
                pass

        log("\n" + "=" * 75)
        log(f"🎬 [KÊNH #{idx}/{len(sources_list)}] BẮT ĐẦU QUÉT: {raw_src}")
        log(f"🎯 Mục tiêu đăng vào Kênh UCircle: [{target_label}]")
        log("=" * 75)

        try:
            links, info = tiktok_extractor.extract_tiktok_links_detailed(
                playwright, target_url, limit, exclude_links=exclude_links
            )
            detected_issue = info.get("reason", "") if info.get("status") != "success" else None
            source_stats[raw_src]["issue"] = detected_issue

            new_for_src = 0
            for lk in links:
                if lk not in seen_in_batch:
                    seen_in_batch.add(lk)
                    all_links.append(lk)
                    link_to_circle[lk] = target_circle
                    link_to_source[lk] = raw_src
                    new_for_src += 1

            source_stats[raw_src]["found"] = new_for_src

            if new_for_src == 0:
                log("\n" + "-" * 75)
                log(f"⚠️⚠️ [CẢNH BÁO KÊNH #{idx}]: KHÔNG TÌM THẤY VIDEO NÀO TỪ: {raw_src}")
                log(f"👉 Lý do: {detected_issue or 'Link kênh sai, tài khoản Riêng Tư, dính Captcha, hoặc video đã trùng lặp'}")
                log(f"👉 [HƯỚNG XỬ LÝ]: Kênh này KHÔNG CÓ video được lưu! Bạn có thể kiểm tra lại link")
                log(f"                 hoặc bấm nút [🔄 Quét lại] riêng kênh #{idx} trên giao diện sau khi quét xong!")
                log("-" * 75 + "\n")
            else:
                log(f"✅ [Kênh #{idx}] Thu thập thành công {new_for_src} video mới hợp lệ.")
        except Exception as e:
            source_stats[raw_src]["error"] = str(e)
            source_stats[raw_src]["issue"] = f"Lỗi ngoại lệ: {e}"
            log(f"❌ [LỖI KÊNH #{idx}] Gặp sự cố khi quét {raw_src}: {e}")

    log(f"\n[+] Đã duyệt qua toàn bộ {len(sources_list)} nguồn TikTok. Tổng cộng: {len(all_links)} video mới tìm thấy.")
    if not all_links:
        failed_sources = []
        for src, st in source_stats.items():
            failed_sources.append({
                "idx": st["idx"],
                "source": src,
                "target_circle": st["target_circle"],
                "found": 0,
                "passed": 0,
                "reason": st.get("issue") or st.get("error") or "Không thu thập được video nào (0 video)",
            })

        log("\n" + "=" * 75)
        log("❌ BÁO CÁO: TẤT CẢ CÁC KÊNH ĐỀU KHÔNG THU ĐƯỢC VIDEO NÀO (0 VIDEO)!")
        log("👉 Vui lòng kiểm tra lại đường truyền mạng, cookie hoặc bấm [🔄 Quét lại] từng kênh.")
        log("=" * 75)

        if on_source_done:
            for src, st in source_stats.items():
                try:
                    on_source_done(st["idx"], src, st["target_circle"], st)
                except Exception:
                    pass

        return {
            "scanned": 0,
            "passed": 0,
            "rejected": 0,
            "sources": len(sources_list),
            "source_stats": source_stats,
            "failed_sources": failed_sources,
        }

    log(f"[+] Đang lấy metadata song song ({scrape_threads} luồng)...")
    passed_rows = []
    rejected = 0

    with ThreadPoolExecutor(max_workers=scrape_threads) as pool:
        futures = {
            pool.submit(_fetch_metadata_staggered, link, cookies_path, browser_cookie): link
            for link in all_links
        }
        for i, future in enumerate(as_completed(futures), 1):
            link = futures[future]
            src = link_to_source.get(link, "")
            try:
                meta = future.result()
            except Exception as e:
                log(f"[ERROR] {link}: {e}")
                meta = {}

            if quality_filter(meta, min_views, min_likes, min_resolution):
                target_circle = link_to_circle.get(link, "")
                if src in source_stats:
                    source_stats[src]["passed"] += 1

                passed_rows.append({
                    "link": meta["link"],
                    "caption": meta["caption"],
                    "hashtags": meta["hashtags"],
                    "views": meta["views"],
                    "likes": meta["likes"],
                    "resolution": f"{meta['width']}x{meta['height']}",
                    "target_circle": target_circle,
                })
                circle_hint = f" [-> {target_circle}]" if target_circle else ""
                log(f"[{i}/{len(all_links)}] ✅ Đạt chất lượng{circle_hint}: {link}")
            else:
                rejected += 1
                if src in source_stats:
                    source_stats[src]["rejected"] += 1
                log(f"[{i}/{len(all_links)}] ⏭️ Loại (không đạt ngưỡng): {link}")

    added = excel_store.append_records(passed_rows)
    if passed_rows:
        dedupe.mark_as_scanned([r["link"] for r in passed_rows])

    if on_source_done:
        for src, st in source_stats.items():
            try:
                on_source_done(st["idx"], src, st["target_circle"], st)
            except Exception:
                pass

    # Tạo danh sách các kênh thất bại (0 video hoặc 0 video đạt chuẩn)
    failed_sources = []
    for src, st in source_stats.items():
        if st["error"]:
            failed_sources.append({
                "idx": st["idx"],
                "source": src,
                "target_circle": st["target_circle"],
                "found": st["found"],
                "passed": st["passed"],
                "reason": f"Lỗi truy cập: {st['error']}",
            })
        elif st["found"] == 0:
            failed_sources.append({
                "idx": st["idx"],
                "source": src,
                "target_circle": st["target_circle"],
                "found": 0,
                "passed": 0,
                "reason": st.get("issue") or "Không thu thập được video nào (0 video)",
            })
        elif st["passed"] == 0:
            failed_sources.append({
                "idx": st["idx"],
                "source": src,
                "target_circle": st["target_circle"],
                "found": st["found"],
                "passed": 0,
                "reason": f"Thu thập được {st['found']} video nhưng 0 video đạt chuẩn tương tác ({st['rejected']} bị loại)",
            })

    log("\n" + "=" * 75)
    log("📊 BẢNG TỔNG HỢP KẾT QUẢ QUÉT THEO TỪNG KÊNH TIKTOK:")
    log("=" * 75)
    for src, st in source_stats.items():
        idx = st["idx"]
        circle = st["target_circle"]
        found = st["found"]
        passed = st["passed"]
        rej = st["rejected"]
        err = st["error"]
        issue = st.get("issue")

        if err:
            log(f"❌ [Hàng #{idx}] {src}  ➡️  UCircle: [{circle}]")
            log(f"   ⚠️ LỖI TRUY CẬP: {err}")
            log(f"   👉 [CẦN QUÉT LẠI]: Bấm nút [🔄 Quét lại] tại Hàng #{idx}!")
        elif found == 0:
            log(f"❌ [Hàng #{idx}] {src}  ➡️  UCircle: [{circle}]")
            log(f"   ⚠️ 0 VIDEO THU THẬP! (Lý do: {issue or 'Trang trống/bị chặn'})")
            log(f"   👉 [CẦN QUÉT LẠI]: Bấm nút [🔄 Quét lại] tại Hàng #{idx}!")
        elif passed == 0:
            log(f"⚠️ [Hàng #{idx}] {src}  ➡️  UCircle: [{circle}]")
            log(f"   ⚠️ Thu thập {found} video nhưng 0 video đạt chuẩn tương tác ({rej} bị loại).")
            log(f"   👉 [LƯU Ý]: Giảm ngưỡng views/likes hoặc bấm [🔄 Quét lại] nếu vừa đổi tiêu chí.")
        else:
            log(f"✅ [Hàng #{idx}] {src}  ➡️  UCircle: [{circle}]")
            log(f"   📹 Thu thập: {found} video | Đạt chuẩn: {passed} video | Loại: {rej} video")
        log("-" * 75)

    log(f"🎯 Tổng kết: Đã lưu {added} video mới vào {config.EXCEL_PATH} (loại {rejected} video).")
    if failed_sources:
        log(f"\n⚠️⚠️ CHÚ Ý: Có {len(failed_sources)} kênh KHÔNG CÓ video đạt chuẩn! Hãy kiểm tra danh sách trên để quét lại.")
    log("=" * 75 + "\n")

    return {
        "scanned": len(all_links),
        "passed": added,
        "rejected": rejected,
        "sources": len(sources_list),
        "source_stats": source_stats,
        "failed_sources": failed_sources,
    }
