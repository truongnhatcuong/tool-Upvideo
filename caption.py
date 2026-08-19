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
