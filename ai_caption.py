"""Sinh và tối ưu caption/hashtag bằng AI cho nền tảng UCircle.
- Mặc định nền tảng: UCircle (thay thế/loại bỏ các từ ngữ đặc thù của TikTok).
- Dựa vào Tên Kênh Circle (target_circle) làm trọng tâm để định hình nội dung và phong cách.
- Cho phép thay đổi/biên tập lại nội dung sẵn có của TikTok để tạo caption hay, tự nhiên và kích thích tương tác.
- Tự động gợi ý 3-5 hashtag chất lượng bám sát kênh Circle, luôn có #ucircle.
API key đọc từ config.AI_API_KEY hoặc biến môi trường API_KEY_AI.
"""

import os
import re
import config


def _api_key() -> str:
    return getattr(config, "AI_API_KEY", "") or os.environ.get("API_KEY_AI", "")


def has_ai_configured() -> bool:
    """Kiểm tra xem đã có API Key AI hay chưa."""
    return bool(_api_key().strip())


def _call_ai(prompt: str):
    api_key = _api_key()
    if not api_key:
        return None

    try:
        import requests
    except ImportError:
        print("[AI] Thiếu thư viện 'requests' -> bỏ qua sinh nội dung AI (pip install requests).")
        return None

    try:
        resp = requests.post(
            getattr(config, "AI_API_URL", "https://api1.shupremium.com/v1/chat/completions"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={
                "model": getattr(config, "AI_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        print(f"[AI] Lỗi khi gọi AI: {e}")
        return None


def generate_ucircle_post(
    tiktok_caption: str = "",
    tiktok_hashtags: str = "",
    circle_name: str = "UCircle",
    extra_context: str = "",
) -> tuple[str | None, str | None]:
    """Tạo hoặc viết lại Caption và Hashtags chuẩn chỉnh cho nền tảng UCircle dựa vào Tên Kênh Circle.
    
    - circle_name: Tên kênh Circle mục tiêu (vd: 'Xe Độ', 'Gái Xinh', 'Hài Hước'...). Nếu không có thì mặc định là 'UCircle'.
    - tiktok_caption: Nội dung text sẵn có từ TikTok (sẽ được AI biên tập, thay đổi, làm mới cho phù hợp).
    - tiktok_hashtags: Hashtags gốc từ TikTok.
    - extra_context: Ngữ cảnh phụ như tiêu đề video, tác giả, id video.
    
    Trả về (caption, hashtags) hoặc (None, None) nếu AI lỗi.
    """
    c_name = (circle_name or "").strip() or "UCircle"

    prompt = f"""Bạn là chuyên gia sáng tạo nội dung cho mạng xã hội UCircle.
Nhiệm vụ: Viết Caption và Hashtags tiếng Việt ngắn gọn, hấp dẫn để đăng video vào Kênh Circle: [{c_name}].

Dữ liệu tham khảo từ TikTok:
- Tên kênh Circle mục tiêu: {c_name}
- Caption sẵn có từ TikTok: {tiktok_caption or '(Không có)'}
- Hashtag sẵn có từ TikTok: {tiktok_hashtags or '(Không có)'}
- Ngữ cảnh bổ sung: {extra_context or '(Không có)'}

YÊU CẦU QUAN TRỌNG:
1. TRỌNG TÂM KÊNH CIRCLE: Dựa vào Tên Kênh Circle [{c_name}] để định hình chủ đề, phong cách, giọng văn (hài hước, thả thính, xe cộ, kiến thức...) thật cuốn hút.
2. THAY ĐỔI & BIÊN TẬP NỘI DUNG TIKTOK: 
   - Bạn ĐƯỢC PHÉP thay đổi, viết lại, làm mới nội dung sẵn có của TikTok cho tự nhiên, mượt mà và kích thích tương tác hơn.
   - TUYỆT ĐỐI LOẠI BỎ mọi từ ngữ/liên kết liên quan đến TikTok (như 'follow tiktok', 'fl tiktok', 'link bio', 'thả tim tiktok', '@user'...); chuyển đổi hoàn toàn sang phong cách mạng xã hội UCircle.
   - Nếu nội dung TikTok bị trống, hãy tự sáng tạo 1 caption mới toanh thật hay đúng chủ đề kênh [{c_name}].
   - Caption chỉ từ 1 - 2 câu ngắn gọn, KHÔNG chứa hashtag trong caption.
3. HASHTAGS:
   - Gợi ý 3 - 5 hashtags chất lượng bám sát tên kênh Circle [{c_name}] và chủ đề video.
   - Luôn có hashtag #ucircle và hashtag liên quan trực tiếp đến tên kênh Circle (viết liền không dấu, ví dụ kênh 'Gái Xinh' -> #gaixinh).
   - Mỗi hashtag bắt đầu bằng ký tự #, cách nhau bằng dấu cách.

TRẢ LỜI ĐÚNG 2 DÒNG (không chào hỏi, không giải thích gì thêm):
Dòng 1: [Nội dung Caption]
Dòng 2: [Các hashtag cách nhau bằng dấu cách]"""

    content = _call_ai(prompt)
    if not content:
        return None, None

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return None, None

    caption = lines[0]
    # Làm sạch ngoặc kép nếu AI vô tình bọc vào
    caption = re.sub(r'^[“"\'‘](.+)[”"\'’]$', r'\1', caption).strip()

    hashtags_line = lines[1] if len(lines) > 1 else ""
    raw_tags = [w for w in hashtags_line.split() if w.startswith("#")]
    
    # Đảm bảo luôn có #ucircle
    tag_lower = [t.lower() for t in raw_tags]
    if "#ucircle" not in tag_lower:
        raw_tags.append("#ucircle")

    hashtags = " ".join(raw_tags)
    return caption or None, hashtags or None


def generate_caption(context: str, circle_name: str = "UCircle"):
    """Sinh hoặc viết lại 1 dòng caption TikTok cho UCircle bám sát tên kênh Circle."""
    caption, _ = generate_ucircle_post(tiktok_caption=context, circle_name=circle_name)
    return caption or None


def generate_hashtags(context: str, circle_name: str = "UCircle"):
    """Sinh 3-5 hashtag cho UCircle bám sát tên kênh Circle."""
    _, hashtags = generate_ucircle_post(tiktok_caption=context, circle_name=circle_name)
    return hashtags or None


def generate_caption_and_hashtags(context: str, circle_name: str = "UCircle"):
    """Sinh cả Caption và Hashtags cho UCircle bám sát tên kênh Circle."""
    return generate_ucircle_post(extra_context=context, circle_name=circle_name)
