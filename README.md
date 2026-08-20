# UCircle & TikTok Automator Pipeline

Phần mềm tự động hóa toàn trình: **Quét kênh TikTok -> Tải Video (bỏ qua logo) -> Đăng tự động lên UCircle**.
Với cơ chế **Cuốn chiếu (Pipeline)**, video được tải về, đăng ngay lập tức, sau đó xóa file tạm khỏi ổ cứng. Tránh tình trạng tải 1000 video làm đầy bộ nhớ và RAM.

## Tính năng nổi bật
- **Giao diện trực quan (GUI):** Dễ dàng cấu hình và theo dõi luồng công việc.
- **Vượt TikTok Anti-Bot:** Tích hợp phương pháp lấy Cookie tĩnh (cookies.txt), giải quyết triệt để lỗi `Failed to decrypt with DPAPI` hoặc `Unable to extract universal data`.
- **Pipeline Siêu nhẹ:** Không tốn tài nguyên ổ cứng. Tải đến đâu, up đến đó, xóa dọn dẹp ngay.
- **Tự động đăng UCircle:** Tự động điều khiển trình duyệt ẩn (Playwright) upload file, ghi chú, tag và chuyển đổi tài khoản cá nhân/fanpage.
- **Chống Trùng Lặp:** Lưu trữ danh sách đã tải trong `data/posted.json` và `data/downloaded.json` để không tải/đăng lại video cũ ở các lần chạy sau.

## Cài đặt (Chỉ làm 1 lần)

1. Mở Terminal/CMD tại thư mục `ucircle-py`:
```bash
pip install -r requirements.txt
playwright install chromium
```

## Cách chạy phần mềm

Mở Terminal và gõ:
```bash
python gui.py
```
Giao diện phần mềm sẽ hiện ra.

## Hướng dẫn lấy Cookie TikTok (Bắt buộc)
Do TikTok cập nhật bảo mật (App-Bound Encryption), tool không thể tự động "hút" cookie từ trình duyệt đang mở. Bạn cần cấp cho tool file `cookies.txt` theo các bước sau:

1. Mở Chrome, cài đặt Extension: **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)**
2. Truy cập vào trang web `tiktok.com` và **đăng nhập** tài khoản của bạn (để mở khóa chặn xem video).
3. Bấm vào biểu tượng Extension "Get cookies.txt LOCALLY" ở góc phải trình duyệt, chọn **Export**.
4. Lưu file `tiktok_cookies.txt` về máy.
5. Trên giao diện Tool `gui.py`, tại mục **Cookie File**, bấm **Browse** và chọn file `tiktok_cookies.txt` vừa tải về.

## Cấu hình nâng cao (Tuỳ chọn)
- Nếu cần thay đổi độ trễ giữa các lần đăng (để tránh bị UCircle đánh dấu spam), bạn mở file `config.py` và chỉnh sửa:
  ```python
  MIN_DELAY_SEC = 25  # Thời gian chờ tối thiểu (giây)
  MAX_DELAY_SEC = 40  # Thời gian chờ tối đa (giây)
  ```
- File `config.py` cũng chứa các XPath (Selectors) của web UCircle. Nếu UCircle đổi giao diện, bạn chỉ cần cập nhật lại selector ở đây mà không cần sửa code cốt lõi.

## Xử lý sự cố (Troubleshooting)
- **Lỗi không lấy được video TikTok:** Đảm bảo file `cookies.txt` của bạn còn hạn (chưa bị đăng xuất trên web). Thử vào lại TikTok, export file cookie mới và nạp lại vào tool.
- **Tool đăng lên UCircle nhưng bị dừng giữa chừng:** Theo dõi cửa sổ Chromium (chế độ Headless=False) xem có bị kẹt ở bước chọn Fanpage hay hashtag không. Nếu kẹt, cập nhật lại DOM Selector trong `config.py`.
