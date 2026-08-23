"""Sinh caption/hashtag bằng AI khi video TikTok thiếu 1 trong 2 hoặc thiếu cả 2.
Cùng endpoint/kiểu gọi với d:\\nextjs\\ai-powered-orm\\lib\\keyAI.ts (OpenAI-compatible
chat completions). API key đọc từ config.AI_API_KEY hoặc biến môi trường API_KEY_AI.
Nếu chưa có key / lỗi, mọi hàm trả về None (bên gọi tự bỏ qua video đó)."""

import os
import config


def _api_key() -> str:
    return getattr(config, "AI_API_KEY", "") or os.environ.get("API_KEY_AI", "")


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
            getattr(config, "AI_API_URL", "https://gpt1.shupremium.com/v1/chat/completions"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={
                "model": getattr(config, "AI_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        print(f"[AI] Lỗi khi gọi AI: {e}")
        return None


def generate_caption(context: str):
    """Thiếu CAPTION, đã có hashtag/ngữ cảnh -> sinh 1 dòng caption đúng chủ đề."""
    prompt = (
        "Viết đúng 1 dòng caption TikTok ngắn gọn, tự nhiên, hấp dẫn bằng tiếng Việt, "
        f"đúng chủ đề với ngữ cảnh sau: {context}. "
        "Chỉ trả về đúng nội dung caption, KHÔNG kèm hashtag, KHÔNG giải thích thêm."
    )
    content = _call_ai(prompt)
    return content or None


def generate_hashtags(context: str):
    """Thiếu HASHTAG, đã có caption -> sinh 3-5 hashtag đúng chủ đề với caption đó."""
    prompt = (
        "Dựa vào caption TikTok sau: "
        f"'{context}', hãy gợi ý 3-5 hashtag tiếng Việt/tiếng Anh phổ biến, ĐÚNG CHỦ ĐỀ. "
        "Chỉ trả về đúng 1 dòng các hashtag cách nhau bằng dấu cách, mỗi hashtag bắt đầu bằng #, "
        "KHÔNG giải thích thêm."
    )
    content = _call_ai(prompt)
    if not content:
        return None
    hashtags = " ".join(w for w in content.split() if w.startswith("#"))
    return hashtags or None


def generate_caption_and_hashtags(context: str):
    """Thiếu CẢ caption lẫn hashtag -> sinh cả 2 dựa theo ngữ cảnh (tên kênh/tiêu đề...).
    Trả về (caption, hashtags) hoặc (None, None)."""
    prompt = (
        "Video TikTok này không có caption và không có hashtag. Dựa vào ngữ cảnh sau: "
        f"'{context}', hãy sinh nội dung đăng bài phù hợp, đúng chủ đề, bằng tiếng Việt. "
        "Trả lời ĐÚNG 2 dòng, không thêm gì khác:\n"
        "Dòng 1: caption ngắn gọn tự nhiên (không chứa hashtag)\n"
        "Dòng 2: 3-5 hashtag phù hợp, cách nhau bằng dấu cách, mỗi hashtag bắt đầu bằng #"
    )
    content = _call_ai(prompt)
    if not content:
        return None, None

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return None, None

    caption = lines[0]
    hashtags_line = lines[1] if len(lines) > 1 else ""
    hashtags = " ".join(w for w in hashtags_line.split() if w.startswith("#"))
    return caption or None, hashtags or None
