import os
import random
import config


def title_from_filename(file_path: str) -> str:
    name = os.path.splitext(os.path.basename(file_path))[0]
    return name.replace("_", " ").replace("-", " ").strip()


def generate_caption(file_path: str):
    title = title_from_filename(file_path)
    template = random.choice(config.CAPTION_TEMPLATES)
    description = template.format(title=title)
    hashtags = " ".join(random.sample(config.HASHTAG_POOL, k=min(3, len(config.HASHTAG_POOL))))
    return description, hashtags


def caption_from_record(row: dict):
    """Lấy caption + hashtag THẬT từ dòng dữ liệu Excel (đã quét từ TikTok gốc).
    Nếu TikTok không có caption/hashtag, thử AI sinh dựa theo tên kênh Circle hoặc dùng generate_caption làm fallback."""
    description = (row.get("caption") or "").strip()
    hashtags = (row.get("hashtags") or "").strip()
    target_circle = (row.get("target_circle") or "").strip() or "UCircle"

    if not description or not hashtags:
        try:
            import ai_caption
            if ai_caption.has_ai_configured():
                ai_cap, ai_tags = ai_caption.generate_ucircle_post(
                    tiktok_caption=description,
                    tiktok_hashtags=hashtags,
                    circle_name=target_circle,
                    extra_context=row.get("link", ""),
                )
                if not description and ai_cap:
                    description = ai_cap
                if not hashtags and ai_tags:
                    hashtags = ai_tags
        except Exception:
            pass

    if not description and not hashtags:
        return generate_caption(row.get("link", "video"))

    if not hashtags:
        hashtags = f"#ucircle #{target_circle.replace(' ', '')}"

    return description, hashtags
