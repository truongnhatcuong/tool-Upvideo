# ucircle-auto-uploader (bản Python)

Chạy 1 lệnh/1 click là tool tự mở trình duyệt, đăng nhập (lần đầu), rồi tự lặp đăng video.

## Cài đặt (chỉ làm 1 lần)

```bash
cd ucircle-py
pip install -r requirements.txt
playwright install chromium
```

## Cách chạy

**Windows:** double-click `run_windows.bat`
**macOS:** mở Terminal 1 lần đầu chạy `chmod +x run_mac.command` để cấp quyền thực thi, sau đó double-click `run_mac.command` được luôn
**Hoặc trên mọi hệ điều hành:** mở terminal, gõ `python main.py`

## Lần chạy đầu tiên

Trình duyệt sẽ tự mở ra trang đăng nhập ucircle.net. Bạn đăng nhập tay như bình thường, xong quay lại cửa sổ terminal/cmd, nhấn Enter. Tool lưu session vào `data/session.json` — từ lần sau **không cần đăng nhập lại nữa**, cứ chạy là nó tự vào thẳng, tự đăng video.

## Trước khi chạy thật — 2 việc bắt buộc phải làm

1. **Sửa `config.py`** — phần `SELECTORS`: mở trang upload thật trên Chrome, F12 → Elements → lấy đúng id/name của ô chọn file, ô mô tả, nút đăng, và 1 dấu hiệu báo đăng thành công. (Xem hướng dẫn prompt lấy selector ở tin nhắn trước.)
2. **Bỏ video vào thư mục `videos/`** — hoặc đổi `VIDEO_FOLDER` trong `config.py` thành đường dẫn thư mục video có sẵn trên máy bạn, ví dụ:
   ```python
   VIDEO_FOLDER = r"C:\Users\TenBan\Videos\MyContent"   # Windows
   VIDEO_FOLDER = "/Users/tenban/Movies/MyContent"       # macOS/Linux
   ```

## Video được đọc từ đâu?

Trực tiếp từ ổ đĩa máy bạn — tool không upload video đi đâu để xử lý, nó chạy ngay trên máy, quét thư mục `VIDEO_FOLDER`, tính hash để chống trùng, rồi gắn thẳng file đó vào ô upload trên trình duyệt.

## Dừng tool

Nhấn `Ctrl + C` trong cửa sổ terminal, hoặc đóng cửa sổ đó lại.

## Theo dõi

Xem tiến trình trực tiếp trên terminal, hoặc mở file `data/log.txt` để xem lịch sử log.
