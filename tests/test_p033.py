"""P0.3.3: 2-of-3 availability and cancellation of ambiguous remote submissions.

All tests operate on local synthetic stores, mock roles and loopback HTTP only.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from blindreview.common import ProtocolError
from blindreview.http_client import ReviewClient, TransportError
from blindreview.store import JobStore
from blindreview.worker import ReviewHandler, Worker
from test_pipeline import make_repo


class CancellationTombstone(unittest.TestCase):
    def test_cancel_before_submit_is_persistent_and_rejects_late_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite3"
            store = JobStore(path)
            try:
                self.assertFalse(store.cancel("future-job"))
                self.assertTrue(store.is_tombstoned("future-job"))
                with self.assertRaisesRegex(ProtocolError, "cancelled before submission"):
                    store.submit({"job_id": "future-job", "role": "blind-review"})
                self.assertIsNone(store.get("future-job"))
            finally:
                store.close()
            restored = JobStore(path)
            try:
                self.assertTrue(restored.is_tombstoned("future-job"))
                with self.assertRaises(ProtocolError):
                    restored.submit({"job_id": "future-job", "role": "blind-review"})
                self.assertIsNone(restored.get("future-job"))
            finally:
                restored.close()

    def test_existing_job_cancel_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "store.sqlite3")
            try:
                request = {"job_id": "existing", "role": "blind-review"}
                first, inserted = store.submit(request)
                self.assertTrue(inserted)
                self.assertTrue(store.cancel("existing"))
                self.assertEqual(store.get("existing")["state"], "CANCELLED")
                again, inserted = store.submit(request)
                self.assertFalse(inserted)
                self.assertEqual(again["state"], "CANCELLED")
                self.assertTrue(store.is_tombstoned("existing"))
            finally:
                store.close()


class WorkerCancellationHTTP(unittest.TestCase):
    def test_cancel_unknown_job_blocks_late_http_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            commit = make_repo(source)
            contract = root / "contract.md"
            contract.write_text("Synthetic blind review", encoding="utf-8")
            marker = root / "unwanted-execution"
            worker = Worker({
                "node_id": "fixture-node", "physical_host_id": "fixture-host",
                "workdir": str(root / "worker"), "contract_path": str(contract),
                "repositories": {"fixture": str(source)},
                "harnesses": {"mock": {"command": [
                    sys.executable, "-c",
                    "from pathlib import Path;Path(" + repr(str(marker)) + ").write_text('executed')"
                ]}},
                "max_job_seconds": 10,
            })
            handler = type("OnlyFixtureHandler", (ReviewHandler,), {
                "worker": worker, "token": "synthetic-bearer-unique-token-00001",
            })
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = ReviewClient(f"http://127.0.0.1:{server.server_port}",
                                      "synthetic-bearer-unique-token-00001", timeout=3)
                cancelled = client.cancel("test-late-post")
                self.assertEqual(cancelled["state"], "CANCELLED")
                self.assertEqual(client.status("test-late-post")["state"], "CANCELLED")
                request = {
                    "job_id": "test-late-post", "task_id": "task", "repository": "fixture",
                    "commit_sha": commit,
                    "contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
                    "harness": "mock", "model": "mock", "role": "blind-review",
                }
                with self.assertRaises(TransportError):
                    client.submit(request)
                self.assertIsNone(worker.store.get(request["job_id"]))
                self.assertFalse(marker.exists())
                self.assertTrue(worker.store.is_tombstoned(request["job_id"]))
            finally:
                server.shutdown()
                server.server_close()
                worker.shutdown()
                worker.store.close()


if __name__ == "__main__":
    unittest.main()
