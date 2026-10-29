import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import track_downloads as tracker


def release(count=8, asset_id=1):
    return {"draft": False, "tag_name": "v1", "assets": [
        {"name": "ChiiBar-macOS.zip", "id": asset_id, "download_count": count},
        {"name": "SHA256SUMS.txt", "id": 2, "download_count": 500}]}


class DownloadTests(unittest.TestCase):
    def test_filter_and_korean_date(self):
        item = tracker.snapshot([release()], datetime(2026, 10, 29, 16, tzinfo=timezone.utc))
        self.assertTrue(item["collected_at"].startswith("2026-10-30"))
        self.assertEqual(tracker.total(item), 8)

    def test_increases_and_asset_changes(self):
        old = {"assets": [{"id": 1, "downloads": 8}]}
        self.assertEqual(tracker.increase(old, {"assets": [{"id": 1, "downloads": 10}, {"id": 3, "downloads": 5}]}), 7)
        for assets in [[], [{"id": 1, "downloads": 2}], [{"id": 3, "downloads": 9}]]:
            self.assertIsNone(tracker.increase(old, {"assets": assets}))

    def test_same_day_overwrite_preserves_other_days(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for day, count in [(29, 8), (30, 10), (30, 12)]:
                tracker.save(root, tracker.snapshot([release(count)], datetime(2026, 10, day, tzinfo=tracker.KST)))
            self.assertEqual(len(list((root / "stats/snapshots").glob("*.json"))), 2)
            report = (root / "stats/README.md").read_text()
            self.assertIn("+4", report)
            self.assertIn("기준점", report)
            self.assertEqual(json.loads((root / "stats/snapshots/2026-10-29.json").read_text())["assets"][0]["downloads"], 8)

    def test_invalid_input(self):
        for releases in [[], [release(-1)], [release(), release()]]:
            with self.assertRaises(ValueError):
                tracker.snapshot(releases, datetime.now(tracker.KST))

    def test_pagination_and_network_failure(self):
        from io import BytesIO
        batches = [BytesIO(json.dumps([release()] * 100).encode()), BytesIO(b"[]")]
        with patch.object(tracker, "urlopen", side_effect=batches) as request:
            self.assertEqual(len(tracker.fetch_releases()), 100)
            self.assertIn("page=2", request.call_args.args[0].full_url)
        with patch.object(tracker, "urlopen", side_effect=OSError("network down")):
            with self.assertRaises(OSError):
                tracker.fetch_releases()


if __name__ == "__main__":
    unittest.main()
