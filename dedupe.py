import json
import os
import threading
import config

_lock = threading.Lock()


def _ensure_file(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_posted_set() -> set:
    _ensure_file(config.POSTED_HASH_DB_PATH)
    try:
        with open(config.POSTED_HASH_DB_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


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


# ---- Quản lý lịch sử các video đã từng quét (để tránh quét lại khi vào lại cùng kênh) ----

def load_scanned_set() -> set:
    scanned_path = getattr(config, "SCANNED_DB_PATH", "data/scanned.json")
    _ensure_file(scanned_path)
    try:
        with open(scanned_path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_scanned_set(scanned_set: set):
    scanned_path = getattr(config, "SCANNED_DB_PATH", "data/scanned.json")
    with _lock:
        with open(scanned_path, "w", encoding="utf-8") as f:
            json.dump(sorted(scanned_set), f, ensure_ascii=False, indent=2)


def mark_as_scanned(links):
    """Lưu danh sách link video đã quét vào DB lịch sử."""
    if not links:
        return
    current = load_scanned_set()
    if isinstance(links, (list, set, tuple)):
        current.update(links)
    else:
        current.add(str(links))
    save_scanned_set(current)


def load_all_seen_links() -> set:
    """Trả về toàn bộ link video đã từng quét HOẶC đã từng đăng để né hoàn toàn."""
    return load_posted_set().union(load_scanned_set())
