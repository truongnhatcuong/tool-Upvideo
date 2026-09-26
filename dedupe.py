import json
import os
import re
import threading
import config

_lock = threading.Lock()
POSTED_BY_CIRCLE_PATH = os.path.join(getattr(config, "BASE_DIR", "."), "data", "posted_by_circle.json")


def _ensure_file(path: str, default_content=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([] if default_content is None else default_content, f)


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


def mark_as_posted(link: str, posted_set: set, circle_name: str = None):
    posted_set.add(link)
    save_posted_set(posted_set)
    if circle_name:
        record_posted_for_circle(link, circle_name)


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


def clear_scanned_for_channel(channel_url_or_keyword: str) -> int:
    """Khi quét lại một kênh cụ thể: xoá các link của kênh đó khỏi scanned.json
    (TRỪ các link đã thực sự được đăng trong posted.json) để không bị chặn oan làm lãng phí video."""
    if not channel_url_or_keyword:
        return 0

    # Trích xuất username ví dụ: https://www.tiktok.com/@alominhngheday -> @alominhngheday
    raw = channel_url_or_keyword.strip()
    match = re.search(r"@([a-zA-Z0-9_\.\-]+)", raw)
    user_tag = f"@{match.group(1)}" if match else (raw if raw.startswith("@") else None)

    scanned = load_scanned_set()
    posted = load_posted_set()

    removed = 0
    new_scanned = set()
    for link in scanned:
        # Nếu video đã đăng thật thì giữ lại
        if link in posted:
            new_scanned.add(link)
            continue

        # Nếu link thuộc kênh đang quét lại -> loại khỏi scanned.json để quét lại được
        if user_tag and user_tag.lower() in link.lower():
            removed += 1
        elif raw.lower() in link.lower():
            removed += 1
        else:
            new_scanned.add(link)

    if removed > 0:
        save_scanned_set(new_scanned)
    return removed


# ---- Thống kê số video đã đăng theo từng Circle ----

def _load_posted_by_circle_dict() -> dict:
    _ensure_file(POSTED_BY_CIRCLE_PATH, default_content={})
    try:
        with open(POSTED_BY_CIRCLE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_posted_by_circle_dict(data: dict):
    with _lock:
        with open(POSTED_BY_CIRCLE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def record_posted_for_circle(link: str, circle_name: str):
    """Lưu vết video đã đăng thành công cho một Circle cụ thể."""
    if not circle_name:
        return
    c_name = str(circle_name).strip()
    data = _load_posted_by_circle_dict()
    if c_name not in data:
        data[c_name] = []
    if link not in data[c_name]:
        data[c_name].append(link)
    _save_posted_by_circle_dict(data)


def get_circle_posted_counts() -> dict[str, int]:
    """Trả về số lượng video ĐÃ ĐĂNG của từng Circle: {'Gái Xinh': 42, 'xe độ chiến': 42, ...}."""
    data = _load_posted_by_circle_dict()
    
    # Nếu file posted_by_circle rỗng, tự động quét từ data/log.txt để khởi tạo số liệu lịch sử
    if not data:
        data = _backfill_posted_from_log()
        if data:
            _save_posted_by_circle_dict(data)

    counts = {}
    for c_name, links in data.items():
        counts[c_name] = len(links) if isinstance(links, list) else int(links or 0)
    return counts


def _backfill_posted_from_log() -> dict:
    """Đọc data/log.txt để phục hồi số video đã đăng theo từng Circle từ các phiên trước."""
    log_path = getattr(config, "LOG_PATH", "data/log.txt")
    if not os.path.exists(log_path):
        return {}

    posted_by_circle = {}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Format: [2026-09-17T16:13:57] ✅ ĐĂNG THÀNH CÔNG lên Circle 🏷️ [Gái Xinh]: "https://www.tiktok.com/..."
                m = re.search(r'ĐĂNG THÀNH CÔNG lên Circle 🏷️ \[([^\]]+)\]:\s*"([^"]+)"', line)
                if m:
                    circle_name = m.group(1).strip()
                    link = m.group(2).strip()
                    if circle_name not in posted_by_circle:
                        posted_by_circle[circle_name] = []
                    if link not in posted_by_circle[circle_name]:
                        posted_by_circle[circle_name].append(link)
    except Exception:
        pass
    return posted_by_circle

