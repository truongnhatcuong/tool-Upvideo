import os
import threading
import datetime

import pandas as pd

import config

COLUMNS = [
    "link", "caption", "hashtags", "target_circle", "duration"
]

_lock = threading.Lock()


def _ensure_file():
    os.makedirs(os.path.dirname(config.EXCEL_PATH), exist_ok=True)
    if not os.path.exists(config.EXCEL_PATH):
        pd.DataFrame(columns=COLUMNS).to_excel(config.EXCEL_PATH, index=False)


def _read_df() -> pd.DataFrame:
    _ensure_file()
    df = pd.read_excel(config.EXCEL_PATH, dtype={"link": str, "target_circle": str})
    if "target_circle" not in df.columns:
        df["target_circle"] = ""
    if "duration" not in df.columns:
        df["duration"] = 0
    return df.fillna("")


def append_records(rows: list):
    """rows: list of dict {link, caption, hashtags, views, likes, resolution, target_circle, duration}.
    Bỏ qua các link đã có sẵn trong file (tránh trùng khi quét lại)."""
    if not rows:
        return 0

    with _lock:
        df = _read_df()
        existing_links = set(df["link"].astype(str)) if not df.empty else set()

        new_rows = []
        for r in rows:
            if str(r.get("link")) in existing_links:
                continue
            new_rows.append({
                "link": r.get("link", ""),
                "caption": r.get("caption", ""),
                "hashtags": r.get("hashtags", ""),
                "target_circle": str(r.get("target_circle", "") or "").strip(),
                "duration": int(r.get("duration", 0) or 0),
            })

        if not new_rows:
            return 0

        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df.to_excel(config.EXCEL_PATH, index=False)
        return len(new_rows)


def load_all() -> list:
    with _lock:
        df = _read_df()
    if df.empty:
        return []
    records = df.to_dict(orient="records")
    for r in records:
        if pd.isna(r.get("target_circle")):
            r["target_circle"] = ""
        else:
            r["target_circle"] = str(r["target_circle"]).strip()
    return records


def remove_records_by_target(target_circle: str) -> int:
    """Xoá toàn bộ các dòng thuộc target_circle trong file Excel để nạp video mới."""
    if not target_circle:
        return 0
    with _lock:
        if not os.path.exists(config.EXCEL_PATH):
            return 0
        df = _read_df()
        if df.empty or "target_circle" not in df.columns:
            return 0
        initial_len = len(df)
        df = df[df["target_circle"].astype(str).str.strip() != str(target_circle).strip()]
        removed = initial_len - len(df)
        if removed > 0:
            df.to_excel(config.EXCEL_PATH, index=False)
        return removed


def get_pending_counts_by_circle() -> dict[str, int]:
    """Đếm số lượng video đang chờ đăng (trong Excel và CHƯA có trong posted.json) theo từng Circle."""
    import dedupe
    excluded = dedupe.load_posted_set() | dedupe.load_skipped_set()
    records = load_all()
    from collections import Counter
    counts = Counter()
    for r in records:
        link = str(r.get("link", "")).strip()
        c_name = str(r.get("target_circle", "") or "").strip()
        if c_name and link and link not in excluded:
            counts[c_name] += 1
    return dict(counts)

