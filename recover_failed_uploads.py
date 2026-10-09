"""Recover legacy download failures incorrectly stored as posted.

Preview: python recover_failed_uploads.py --date 2026-10-05
Apply with backup: python recover_failed_uploads.py --date 2026-10-05 --apply
Run while the upload tool is stopped.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil

import config

LINK_RE = re.compile(r'https://www\.tiktok\.com/@[^\s"<>]+/video/\d+')


def find_recoverable_links(log_text, posted, posted_by_circle, excel_links, date):
    """Only recover explicit download failures with no recorded success anywhere."""
    confirmed = {
        link for links in posted_by_circle.values() if isinstance(links, list)
        for link in links
    }
    download_failures = set()
    for line in log_text.splitlines():
        links = set(LINK_RE.findall(line))
        if "ĐĂNG THÀNH CÔNG" in line:
            confirmed.update(links)
        if line.startswith(f"[{date}T") and "Không tải được video" in line:
            download_failures.update(links)
    return (download_failures & posted & excel_links) - confirmed


def recover(date, apply=False):
    import pandas as pd

    datetime.date.fromisoformat(date)
    posted_path = Path(config.POSTED_HASH_DB_PATH)
    posted = set(json.loads(posted_path.read_text(encoding="utf-8")))
    circle_path = Path(config.BASE_DIR) / "data" / "posted_by_circle.json"
    by_circle = json.loads(circle_path.read_text(encoding="utf-8")) if circle_path.exists() else {}
    excel_links = set(pd.read_excel(config.EXCEL_PATH, usecols=["link"])["link"].dropna().astype(str))
    log_text = Path(config.LOG_PATH).read_text(encoding="utf-8", errors="replace")
    recovered = find_recoverable_links(log_text, posted, by_circle, excel_links, date)
    report = {"date": date, "recovered_count": len(recovered), "links": sorted(recovered), "applied": False}
    if apply and recovered:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = posted_path.parent / "backups" / f"recover-{date}-{stamp}"
        backup.mkdir(parents=True)
        shutil.copy2(posted_path, backup / posted_path.name)
        report["applied"] = True
        report["backup"] = str(backup)
        (backup / "recovery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Write a complete replacement, then atomically replace the history file.
        staging = posted_path.with_suffix(".json.tmp")
        staging.write_text(json.dumps(sorted(posted - recovered), ensure_ascii=False, indent=2), encoding="utf-8")
        staging.replace(posted_path)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Log date, YYYY-MM-DD")
    parser.add_argument("--apply", action="store_true", help="Back up and restore failed links to pending")
    args = parser.parse_args()
    result = recover(args.date, args.apply)
    print(f"{'Restored' if result['applied'] else 'Recoverable'}: {result['recovered_count']} videos")
    if result.get("backup"):
        print(f"Backup and recovery report: {result['backup']}")
