import os
import threading
import datetime

import pandas as pd

import config

COLUMNS = [
    "link", "caption", "hashtags", "target_circle"
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
    return df.fillna("")


def append_records(rows: list):
    """rows: list of dict {link, caption, hashtags, views, likes, resolution, target_circle}.
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
