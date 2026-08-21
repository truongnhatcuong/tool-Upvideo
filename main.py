"""
CHẠY TOOL QUÉT LINK TIKTOK & XUẤT EXCEL:
    python main.py
hoặc:
    python main.py <url> [--limit N] [--output path.xlsx]

Ví dụ:
    python main.py https://www.tiktok.com/@vtv24news --limit 20
"""

import os
import sys
import argparse
import datetime
from playwright.sync_api import sync_playwright

import config
from tiktok_extractor import extract_tiktok_links
from exporter import export_to_excel


def log(msg: str):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def open_file_in_os(file_path: str):
    """Mở file tự động trên Windows/macOS/Linux."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(file_path)
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{file_path}"')
        else:
            os.system(f'xdg-open "{file_path}"')
    except Exception as e:
        print(f"[!] Không thể tự mở file: {e}")


def run_interactive():
    print("=" * 60)
    print("  🚀 TIKTOK VIDEO LINK EXTRACTOR -> EXCEL EXPORT")
    print("  Định dạng xuất file: Excel với cột |link|")
    print("=" * 60)

    url = input("👉 Nhập Link TikTok (Kênh/Profile, Video, Hashtag, Search): ").strip()
    if not url:
        print("❌ URL không được để trống!")
        return

    raw_limit = input(f"👉 Giới hạn số lượng video (Mặc định {config.DEFAULT_LIMIT} = Lấy tất cả): ").strip()
    try:
        limit = int(raw_limit) if raw_limit else config.DEFAULT_LIMIT
    except ValueError:
        limit = 0

    cookies_path = config.COOKIES_PATH if os.path.exists(config.COOKIES_PATH) else None

    print("\n⏳ Đang khởi tạo trình duyệt quét link...")
    with sync_playwright() as p:
        links = extract_tiktok_links(
            p,
            url=url,
            limit=limit,
            headless=config.HEADLESS,
            cookies_path=cookies_path,
        )

    if not links:
        log("❌ Không tìm thấy video nào!")
        return

    print(f"\n✅ Đã quét thành công {len(links)} links video!")
    print("📊 Đang xuất dữ liệu ra file Excel format |link|...")

    out_file = export_to_excel(
        links=links,
        column_name=config.EXCEL_COLUMN_NAME,
        export_dir=config.DEFAULT_EXPORT_DIR,
    )

    log(f"🎉 Hoàn tất! File Excel đã được lưu tại: {out_file}")

    # Hỏi user có muốn mở file ngay không
    choice = input("\n👉 Bạn có muốn mở file Excel vừa xuất không? (y/n, mặc định y): ").strip().lower()
    if choice in ("", "y", "yes"):
        open_file_in_os(out_file)


def run_cli(args):
    cookies_path = args.cookies or (config.COOKIES_PATH if os.path.exists(config.COOKIES_PATH) else None)
    
    with sync_playwright() as p:
        links = extract_tiktok_links(
            p,
            url=args.url,
            limit=args.limit,
            headless=args.headless,
            cookies_path=cookies_path,
        )

    if not links:
        print("❌ Không tìm thấy video nào!")
        return

    out_file = export_to_excel(
        links=links,
        output_path=args.output,
        column_name=config.EXCEL_COLUMN_NAME,
        export_dir=config.DEFAULT_EXPORT_DIR,
    )

    print(f"🎉 Đã xuất thành công {len(links)} links ra: {out_file}")


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and "gui" not in sys.argv[1]:
        parser = argparse.ArgumentParser(description="TikTok Link Extractor -> Excel")
        parser.add_argument("url", help="TikTok URL (channel, video, search, etc.)")
        parser.add_argument("--limit", "-l", type=int, default=0, help="Số lượng video tối đa (0 = tất cả)")
        parser.add_argument("--output", "-o", type=str, default=None, help="Đường dẫn file Excel xuất ra")
        parser.add_argument("--cookies", "-c", type=str, default=None, help="Đường dẫn file cookies.txt")
        parser.add_argument("--headless", action="store_true", help="Chạy trình duyệt ẩn")
        args = parser.parse_args()
        run_cli(args)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
