# ==========================================================
# CONFIG — chỉnh các giá trị dưới đây cho đúng với ucircle.net/app
# Mở trang đăng video, bấm F12 (DevTools) > tab Elements để lấy
# đúng selector (id / name / class) của từng phần tử.
# ==========================================================

import os
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# URL đăng nhập và URL trang đăng video
LOGIN_URL = "https://ucircle.net/app/login"
UPLOAD_URL = "https://ucircle.net/app/wavee"  # URL mới user cung cấp

# Nơi lưu phiên đăng nhập (cookies) để không phải login lại mỗi lần chạy
STORAGE_STATE_PATH = os.path.join(BASE_DIR, "data", "session.json")

# Thư mục chứa video tạm cần đăng (chuẩn hoá cho cả Windows và macOS)
DEFAULT_VIDEO_DIR = os.path.join(BASE_DIR, "data", "temp_videos")
VIDEO_FOLDER = os.environ.get("UCIRCLE_VIDEO_FOLDER", DEFAULT_VIDEO_DIR)

# Thư mục lưu video đã đăng thành công
POSTED_FOLDER = os.path.join(BASE_DIR, "videos", "_posted")

# File lưu danh sách hash/link video đã đăng (chống trùng đăng)
POSTED_HASH_DB_PATH = os.path.join(BASE_DIR, "data", "posted.json")

# File lưu lịch sử tất cả video đã quét (chống quét lại video cũ khi quét cùng kênh)
SCANNED_DB_PATH = os.path.join(BASE_DIR, "data", "scanned.json")

# File lưu danh sách các Kênh/Fanpage UCircle đã lưu (Tên + ID)
IDENTITIES_PATH = os.path.join(BASE_DIR, "data", "identities.json")

# Thư mục lưu hồ sơ trình duyệt TikTok (cookies, thiết bị để không bị hỏi Captcha liên tục)
TIKTOK_PROFILE_DIR = os.path.join(BASE_DIR, "data", "tiktok_profile")

# File log
LOG_PATH = os.path.join(BASE_DIR, "data", "log.txt")

# ---- CẤU HÌNH ĐĂNG NHIỀU KÊNH UCIRCLE ----
# Danh sách ID các kênh được chọn để đăng (có thể chọn 1 hoặc nhiều)
SELECTED_IDENTITIES = ["me"]

# Chế độ phân phối khi chọn nhiều kênh:
#  - "round_robin": xoay vòng (chia đều video cho các kênh)
#  - "all": đăng mỗi video lên TẤT CẢ các kênh đã chọn
DISTRIBUTION_MODE = "round_robin"

# Tư cách đăng mặc định đơn lẻ (nếu chỉ dùng 1 kênh)
IDENTITY_NAME = "me"

# ---- SELECTOR trên trang upload (PHẢI SỬA cho đúng site thật) ----
SELECTORS = {
    "create_button": 'a[data-wavee-create="true"]',  # Nút "Đăng Sóng"
    "tab_file": 'button[data-wavee-upload-tab="file"]', # Nút tab "Tải lên"
    "file_input": 'input[type="file"]',
    "description_box": 'textarea[data-wavee-upload-caption="true"]',
    "hashtag_add_button": 'button[data-wavee-upload-add-tag="true"]',
    "submit_button": 'button[data-wavee-upload-post="true"]', # Nút "Đăng" cuối cùng
    "crosspost_button": 'button[data-wavee-upload-crosspost]', # Nút "Lên bảng tin"
    "success_indicator": 'button[data-wavee-upload-again="true"]', # Nút "Đăng video khác" làm dấu hiệu thành công
}

# Tùy chọn đăng lên Bảng tin (True = Bật, False = Tắt)
CROSSPOST_TO_FEED = True

# ---- Cấu hình vòng lặp ----
MIN_DELAY_SEC = 60     # delay tối thiểu giữa 2 lần đăng (giảm xuống 2 giây để tăng tốc)
MAX_DELAY_SEC = 70     # delay tối đa (5 giây)
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

# Làm chậm mỗi thao tác Playwright (mở trang, click, gõ...) bao nhiêu mili-giây
# để mắt thường theo kịp trình tự thao tác trên UCircle. 0 = chạy nhanh hết cỡ.
SLOW_MO_MS = 0

# ---- File Excel lưu kết quả quét (link, caption, hashtag thật, chỉ số chất lượng) ----
EXCEL_PATH = os.path.join(BASE_DIR, "data", "export_data.xlsx")

# ---- Số luồng xử lý song song (có thể chỉnh trong GUI) ----
SCRAPE_THREADS_DEFAULT = 3   # số luồng lấy metadata (yt-dlp --dump-json) song song
                              # để cao dễ bị TikTok chặn (lỗi "Unable to extract universal data") khi không có cookie
UPLOAD_THREADS_DEFAULT = 1   # số luồng đăng video lên UCircle song song (mỗi luồng 1 browser riêng)

# ---- Ngưỡng lọc chất lượng mặc định (chỉnh trong GUI được) ----
MIN_VIEWS = 1000
MIN_LIKES = 10
MIN_RESOLUTION_HEIGHT = 720  # chiều cao video tối thiểu (px), vd 720 = HD

# ---- AI sinh caption khi video không có nội dung chữ thật (chỉ có hashtag) ----
# Cùng kiểu endpoint với lib/keyAI.ts (OpenAI-compatible chat completions).
# Điền AI_API_KEY sau khi có key, hoặc set biến môi trường API_KEY_AI.
AI_API_KEY = ""
AI_API_URL = "https://gpt4.shupremium.com/v1/chat/completions"
AI_MODEL = "gpt-4o-mini"