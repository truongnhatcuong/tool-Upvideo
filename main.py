"""
CHẠY: python main.py

Đọc danh sách video "pending" đã quét & lọc chất lượng trong file Excel
(config.EXCEL_PATH), rồi đăng tự động lên UCircle bằng nhiều luồng song song
(config.UPLOAD_THREADS_DEFAULT). Muốn quét dữ liệu mới trước, chạy gui.py
và bấm "Quét & Lọc -> Excel" trước khi chạy file này.
"""

import uploader


if __name__ == "__main__":
    uploader.run_uploads()
