# ==========================================================
# CONFIG — chỉnh các giá trị dưới đây cho đúng với ucircle.net/app
# Mở trang đăng video, bấm F12 (DevTools) > tab Elements để lấy
# đúng selector (id / name / class) của từng phần tử.
# ==========================================================

# URL đăng nhập và URL trang đăng video
LOGIN_URL = "https://ucircle.net/app/login"
UPLOAD_URL = "https://ucircle.net/app/wavee"  # URL mới user cung cấp

# Nơi lưu phiên đăng nhập (cookies) để không phải login lại mỗi lần chạy
STORAGE_STATE_PATH = "data/session.json"

# Thư mục chứa video cần đăng — có thể đổi thành đường dẫn tuyệt đối,
# ví dụ Windows: r"C:\Users\TenBan\Videos\MyContent"
# macOS/Linux:  "/Users/tenban/Movies/MyContent"
VIDEO_FOLDER = r"D:\videos"

# Thư mục lưu video đã đăng thành công (tool tự move vào đây)
POSTED_FOLDER = "videos/_posted"

# File lưu danh sách hash video đã đăng (chống trùng)
POSTED_HASH_DB_PATH = "data/posted.json"

# File log
LOG_PATH = "data/log.txt"

# ---- CHỌN TƯ CÁCH ĐĂNG (TRANG CÁ NHÂN HAY FANPAGE) ----
# Gõ CHÍNH XÁC tên hiển thị trên web. 
# Ví dụ: "Tôi" (nếu muốn đăng cá nhân) hoặc "xe hay" (nếu muốn đăng page)
IDENTITY_NAME = "Gái Xinh"

# ---- SELECTOR trên trang upload (PHẢI SỬA cho đúng site thật) ----
SELECTORS = {
    "create_button": 'a[data-wavee-create="true"]',  # Nút "Đăng Sóng"
    "tab_file": 'button[data-wavee-upload-tab="file"]', # Nút tab "Tải lên"
    "file_input": 'input[type="file"]',
    "description_box": 'textarea[data-wavee-upload-caption="true"]',
    "hashtag_add_button": 'button[data-wavee-upload-add-tag="true"]',
    "submit_button": 'button[data-wavee-upload-post="true"]', # Nút "Đăng" cuối cùng
    "success_indicator": 'button[data-wavee-upload-again="true"]', # Nút "Đăng video khác" làm dấu hiệu thành công
}

# ---- Cấu hình vòng lặp ----
MIN_DELAY_SEC = 10     # delay tối thiểu giữa 2 lần đăng (10 giây)
MAX_DELAY_SEC = 15     # delay tối đa (30 giây)
MAX_RETRIES_PER_VIDEO = 2

# ---- Hashtag & caption ----
HASHTAG_POOL = ["#trend", "#xuhuong", "#giaitri"]
CAPTION_TEMPLATES = [
    " đừng bỏ lỡ nhé!",
    " xem ngay hôm nay 🚀",
    "Video mới hôm nay ✨",
]

# Chạy trình duyệt ẩn (True) hay hiện cửa sổ ra để bạn xem quá trình (False)
HEADLESS = False
