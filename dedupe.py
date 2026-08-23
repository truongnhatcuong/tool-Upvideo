import json
import os
import threading
import config

_lock = threading.Lock()


def _ensure_db():
    os.makedirs(os.path.dirname(config.POSTED_HASH_DB_PATH), exist_ok=True)
    if not os.path.exists(config.POSTED_HASH_DB_PATH):
        with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_posted_set() -> set:
    _ensure_db()
    with open(config.POSTED_HASH_DB_PATH, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_posted_set(posted_set: set):
    with _lock:
        with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(posted_set), f, ensure_ascii=False, indent=2)


def is_duplicate(link: str, posted_set: set) -> bool:
    """Dedupe theo link TikTok gốc (ổn định, không cần tải file mới biết trùng)."""
    return link in posted_set


def mark_as_posted(link: str, posted_set: set):
    posted_set.add(link)
    save_posted_set(posted_set)
