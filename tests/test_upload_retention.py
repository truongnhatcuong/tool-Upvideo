import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import config
import dedupe
import excel_store
import uploader
from recover_failed_uploads import find_recoverable_links, recover


class UploadRetentionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.folder = folder
        self.stack.enter_context(patch.multiple(
            config, BASE_DIR=str(folder), EXCEL_PATH=str(folder / "videos.xlsx"),
            POSTED_HASH_DB_PATH=str(folder / "posted.json"),
            LOG_PATH=str(folder / "log.txt"), VIDEO_FOLDER=str(folder / "temp"),
            STOP_REQUESTED=False, MAX_CONSECUTIVE_UPLOAD_FAILURES=3,
        ))
        self.stack.enter_context(patch.multiple(
            dedupe, POSTED_BY_CIRCLE_PATH=str(folder / "data" / "posted_by_circle.json"),
            SKIPPED_PATH=str(folder / "skipped.json"),
        ))
        self.stack.enter_context(patch.object(uploader, "sync_playwright", MagicMock()))
        self.stack.enter_context(patch.object(uploader, "ensure_logged_in"))
        self.stack.enter_context(patch.object(uploader, "log"))
        self.stack.enter_context(patch.object(uploader.time, "sleep"))
        self.stack.enter_context(patch.object(uploader, "random_delay_sec", return_value=0))
        self.stack.enter_context(patch.object(uploader.identity_manager, "get_identity_name", side_effect=lambda cid: cid))

    def rows(self, count, circle="A"):
        rows = [{"link": f"https://www.tiktok.com/@test/video/{i}", "target_circle": circle} for i in range(count)]
        excel_store.append_records(rows)
        return rows

    def run_uploads(self, worker, mode="round_robin", identities=None):
        with patch.object(uploader, "_upload_worker", side_effect=worker) as mock:
            result = uploader.run_uploads(threads=2, identities=identities or ["A"], distribution_mode=mode)
        return result, mock

    def test_network_failures_remain_pending_and_pause_circle(self):
        self.rows(6)
        before = Path(config.EXCEL_PATH).read_bytes()
        result, worker = self.run_uploads(lambda *args: False)
        self.assertEqual(worker.call_count, 6)  # 3 videos, 2 attempts each
        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["remaining"], 6)
        self.assertEqual(result["paused_circles"], ["A"])
        self.assertEqual(dedupe.load_posted_set(), set())
        self.assertEqual(excel_store.get_pending_counts_by_circle(), {"A": 6})
        self.assertEqual(Path(config.EXCEL_PATH).read_bytes(), before)

    def test_failed_video_is_retried_next_run_without_reposting_success(self):
        rows = self.rows(2)
        result, _ = self.run_uploads(lambda rec, *args: rec["link"] == rows[1]["link"])
        self.assertEqual((result["success"], result["failed"], result["remaining"]), (1, 1, 1))
        result, worker = self.run_uploads(lambda *args: True)
        self.assertEqual(result["success"], 1)
        self.assertEqual(worker.call_args.args[0]["link"], rows[0]["link"])
        self.assertEqual(excel_store.get_pending_counts_by_circle(), {})

    def test_stop_keeps_in_flight_video_without_counting_failure(self):
        self.rows(2)
        def stop(*args):
            config.STOP_REQUESTED = True
            return False
        result, worker = self.run_uploads(stop)
        self.assertEqual(worker.call_count, 1)
        self.assertTrue(result["stopped"])
        self.assertEqual((result["failed"], result["remaining"]), (0, 2))
        self.assertEqual(dedupe.load_posted_set(), set())

    def test_stop_during_retry_delay_keeps_record(self):
        self.rows(1)
        def sleep(seconds):
            if seconds == 3:
                config.STOP_REQUESTED = True
        with patch.object(uploader.time, "sleep", side_effect=sleep):
            result, worker = self.run_uploads(lambda *args: False)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual((result["remaining"], result["failed"]), (1, 0))
        self.assertEqual(dedupe.load_posted_set(), set())

    def test_quota_stop_keeps_failed_video(self):
        self.rows(1)
        def quota(*args):
            config.UPLOAD_QUOTA_EXHAUSTED = True
            config.STOP_REQUESTED = True
            return False
        result, _ = self.run_uploads(quota)
        self.assertEqual((result["failed"], result["remaining"]), (0, 1))
        self.assertEqual(dedupe.load_posted_set(), set())

    def test_permanent_rejection_is_separate_from_posted(self):
        rows = self.rows(1)
        rows[0]["duration"] = config.MAX_DURATION_SEC + 1
        with patch.object(uploader, "download_single_video") as download:
            self.assertFalse(uploader._upload_worker(rows[0], "A", None, None))
            download.assert_not_called()
        self.assertEqual(dedupe.load_posted_set(), set())
        self.assertEqual(dedupe.load_skipped_set(), {rows[0]["link"]})
        self.assertEqual(excel_store.get_pending_counts_by_circle(), {})

    def test_skipped_counts_do_not_reduce_success_history(self):
        rows = self.rows(2)
        def worker(rec, *args):
            if rec["link"] == rows[0]["link"]:
                dedupe.mark_as_skipped(rec["link"], "too large")
                return False
            return True
        result, _ = self.run_uploads(worker)
        self.assertEqual((result["skipped"], result["failed"], result["remaining"]), (1, 0, 0))
        self.assertEqual(dedupe.load_posted_set(), {rows[1]["link"]})

    def test_oversized_file_is_skipped_without_marking_posted(self):
        rows = self.rows(1)
        def download(link, path, *args):
            Path(path).write_bytes(b"video")
            return True
        with patch.object(config, "MAX_FILE_SIZE_MB", 0), patch.object(uploader, "download_single_video", side_effect=download):
            self.assertFalse(uploader._upload_worker(rows[0], "A", None, None))
        self.assertEqual(dedupe.load_posted_set(), set())
        self.assertEqual(dedupe.load_skipped_set(), {rows[0]["link"]})
        self.assertEqual(list(Path(config.VIDEO_FOLDER).iterdir()), [])

    def test_same_link_parallel_downloads_use_separate_temp_files(self):
        rows = self.rows(1)
        with patch.object(uploader, "download_single_video", return_value=False) as download:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda cid: uploader._upload_worker(rows[0], cid, None, None), ["A", "B"]))
        paths = [call.args[1] for call in download.call_args_list]
        self.assertEqual(len(set(paths)), 2)

    def test_all_mode_partial_success_resumes_only_failed_circle(self):
        rows = self.rows(1, circle="")
        result, _ = self.run_uploads(lambda rec, cid, *args: cid == "A", "all", ["A", "B"])
        self.assertEqual((result["success"], result["failed"], result["remaining"]), (1, 1, 1))
        self.assertEqual(dedupe.load_posted_set(), set())
        self.assertTrue(dedupe.is_posted_for_circle(rows[0]["link"], "A"))
        result, worker = self.run_uploads(lambda *args: True, "all", ["A", "B"])
        self.assertEqual((result["total"], result["success"], result["remaining"]), (1, 1, 0))
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(worker.call_args.args[1], "B")
        self.assertEqual(dedupe.load_posted_set(), {rows[0]["link"]})

    def test_all_mode_total_failure_retains_and_pauses(self):
        self.rows(5, circle="")
        result, worker = self.run_uploads(lambda *args: False, "all", ["A", "B"])
        self.assertEqual(worker.call_count, 12)
        self.assertEqual((result["failed"], result["remaining"]), (6, 10))
        self.assertEqual(result["paused_circles"], ["A", "B"])
        self.assertEqual(dedupe.load_posted_set(), set())

    def test_concurrent_success_preserves_all_history(self):
        def success(i):
            dedupe.mark_as_posted(str(i), set(), circle_name=str(i % 2))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(success, range(40)))
        self.assertEqual(dedupe.load_posted_set(), {str(i) for i in range(40)})
        self.assertEqual(dedupe.get_circle_posted_counts(), {"0": 20, "1": 20})

    def test_paused_circle_does_not_stop_healthy_circle(self):
        rows = self.rows(5, circle="A")
        excel_store.append_records([{"link": "https://www.tiktok.com/@other/video/99", "target_circle": "B"}])
        result, _ = self.run_uploads(lambda rec, cid, *args: cid == "B")
        self.assertEqual((result["success"], result["remaining"]), (1, 5))
        self.assertEqual(result["paused_circles"], ["A"])
        self.assertEqual(excel_store.get_pending_counts_by_circle(), {"A": len(rows)})

    def test_recovery_preserves_success_from_any_date_and_circle(self):
        links = [f"https://www.tiktok.com/@test/video/{i}" for i in range(5)]
        log = "\n".join(f"[2026-10-05T13:00:00] ❌ Không tải được video: {link}" for link in links)
        log += f'\n[2026-10-06T14:00:00] ✅ ĐĂNG THÀNH CÔNG lên Circle: "{links[1]}"'
        recovered = find_recoverable_links(log, set(links[:4]), {"A": [links[2]]}, set(links[:3]), "2026-10-05")
        self.assertEqual(recovered, {links[0]})
        self.assertEqual(find_recoverable_links(log, set(links), {}, set(links), "2026-10-04"), set())

    def test_recovery_backup_and_apply_are_idempotent(self):
        rows = self.rows(1)
        link = rows[0]["link"]
        dedupe.mark_as_posted(link, set())
        Path(config.LOG_PATH).write_text(f"[2026-10-05T13:00:00] ❌ Không tải được video: {link}", encoding="utf-8")
        preview = recover("2026-10-05")
        self.assertEqual(preview["recovered_count"], 1)
        self.assertFalse(preview["applied"])
        self.assertEqual(dedupe.load_posted_set(), {link})
        result = recover("2026-10-05", apply=True)
        self.assertTrue(result["applied"])
        self.assertEqual(json.loads((Path(result["backup"]) / "posted.json").read_text()), [link])
        self.assertEqual(dedupe.load_posted_set(), set())
        self.assertEqual(recover("2026-10-05", apply=True)["recovered_count"], 0)


if __name__ == "__main__":
    unittest.main()
