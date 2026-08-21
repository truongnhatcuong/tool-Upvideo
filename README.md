# TikTok Video Link Extractor -> Xuất Excel

Công cụ tự động quét danh sách liên kết (link) video TikTok từ trang cá nhân (kênh), video, hashtag, hoặc tìm kiếm và xuất ra file Excel (`.xlsx`) với định dạng cột `|link|`.

---

## 🌟 Tính năng chính

- **Quét link TikTok hàng loạt:** Hỗ trợ quét kênh profile (`@username`), hashtag, tìm kiếm hoặc link video lẻ.
- **Xuất file Excel (`.xlsx` / `.csv`):** Xuất toàn bộ danh sách link sang file Excel chuẩn định dạng cột `|link|` (cột đầu tiên tên là `link`).
- **Giao diện trực quan (GUI) & Dòng lệnh (CLI):** Cung cấp cả ứng dụng đồ họa hiện đại (`gui.py`) lẫn lệnh terminal (`main.py`).
- **Tự động mở file:** Tùy chọn tự động mở file Excel và thư mục `exports/` ngay sau khi quét xong.
- **Hỗ trợ Cookie:** Nhập file `cookies.txt` (Netscape format) nếu TikTok yêu cầu xác minh / đăng nhập.

---

## 🛠️ Cài đặt (Chỉ làm 1 lần)

1. Mở Terminal / Command Prompt tại thư mục dự án và cài đặt các thư viện cần thiết:
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 🚀 Hướng dẫn sử dụng

### Cách 1: Sử dụng Giao diện đồ họa (Khuyên dùng)
- Trên Windows: Nhấp đúp chuột vào file **`run_windows.bat`** hoặc mở terminal gõ:
```bash
python gui.py
```
- **Các bước thực hiện:**
  1. Nhập link kênh/profile TikTok (ví dụ: `https://www.tiktok.com/@vtv24news`).
  2. Điền số lượng video tối đa cần lấy (nhập `0` để quét tất cả video của kênh).
  3. Bấm nút **"🚀 BẮT ĐẦU QUÉT & XUẤT EXCEL"**.
  4. Tool sẽ tự động cuộn trang, thu thập toàn bộ link video và lưu vào thư mục `exports/` rồi mở file Excel cho bạn.

---

### Cách 2: Sử dụng Dòng lệnh (CLI)
Chạy trực tiếp:
```bash
python main.py
```
hoặc truyền trực tiếp tham số:
```bash
# Quét 50 video từ kênh và lưu vào file chỉ định:
python main.py https://www.tiktok.com/@vtv24news --limit 50 --output exports/danh_sach.xlsx

# Quét tất cả video:
python main.py https://www.tiktok.com/@vtv24news
```

---

## 📁 Cấu trúc file xuất Excel
File Excel được lưu trong thư mục `exports/` với cấu trúc chuẩn:
| link |
| :--- |
| `https://www.tiktok.com/@username/video/7123456789012345678` |
| `https://www.tiktok.com/@username/video/7123456789012345679` |
| `https://www.tiktok.com/@username/video/7123456789012345680` |
