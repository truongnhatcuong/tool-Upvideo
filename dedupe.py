import hashlib
import json
import os
import config


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
    with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(posted_set), f, ensure_ascii=False, indent=2)


def hash_file(file_path: str) -> str:
    """Hash theo NỘI DUNG file (không phải tên file) -> đổi tên video vẫn phát hiện trùng."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate(file_path: str, posted_set: set) -> bool:
    return hash_file(file_path) in posted_set


def mark_as_posted(file_path: str, posted_set: set):
    posted_set.add(hash_file(file_path))
    save_posted_set(posted_set)
