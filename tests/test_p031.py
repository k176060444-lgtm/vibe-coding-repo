"""P0.3.1 regressions: legacy-coordinator rejection, deep JSON and Windows spawn race.

No production machine, model or external network is touched.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from blindreview.common import sha256_bytes
from blindreview.http_client import ReviewClient, TransportError
from blindreview.worker import ReviewHandler, Worker
from test_pipeline import make_repo


class ProtocolVersionTests(unittest.TestCase):
    def test_pre_v3_coordinator_cannot_use_new_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "source"
            repo.mkdir()
            make_repo(repo)
            contract = root / "contract.md"
            contract.write_text("Approved only for fixture", encoding="utf-8")
            worker = Worker({
                "node_id": "host-A", "physical_host_id": "physical-A",
                "workdir": str(root / "worker"),
                "contract_path": str(contract),
                "repositories": {"fixture": str(repo)},
                "harnesses": {"fixture": {"command": [sys.executable, "-c", "pass"]}}
            })
            token = "synthetic-protocol-secret-token-123456"
            handler = type("IsolatedWorkerHandler", (ReviewHandler,),
                           {"worker": worker, "token": token})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                # The old P0.2 ReviewClient sends no protocol header.
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                conn.request("GET", "/v1/jobs/test", headers={
                    "Authorization": "Bearer " + token})
                response = conn.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 426)
                self.assertEqual(payload["required_protocol"], "3")
                conn.close()

                # POST must also fail closed, without ever creating a Job ID.
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                conn.request("POST", "/v1/jobs", body=b"{}", headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 426)
                response.read()
                conn.close()
                self.assertEqual(worker.store.unfinished(), [])

                # Current P0.3.1 client is recognized (unknown job becomes 404,
                # not a protocol 426). No model or harness is actually invoked.
                client = ReviewClient(f"http://127.0.0.1:{server.server_port}", token, timeout=2)
                with self.assertRaises(TransportError) as ctx:
                    client.status("missing")
                self.assertIn("HTTP status 404", str(ctx.exception))
            finally:
                server.shutdown()
                server.server_close()
                worker.shutdown()
                worker.store.close()

    def test_deeply_nested_response_is_normalized(self):
        payload = ("[" * 1400 + "]" * 1400).encode("ascii")

        class Deep(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Deep)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = ReviewClient(f"http://127.0.0.1:{server.server_port}",
                                  "synthetic-token", timeout=2)
            with self.assertRaises(TransportError) as ctx:
                client.status("test")
            self.assertIn("RecursionError", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()


@unittest.skipUnless(os.name == "nt", "Kernel Job Object test requires native Windows")
class WindowsLaunchRaceTests(unittest.TestCase):
    def test_immediate_child_spawn_repeatedly_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "source"
            repo.mkdir()
            commit = make_repo(repo)
            contract = root / "contract.md"
            contract.write_text("Read-only mock test", encoding="utf-8")
            child = ("import sys,time;from pathlib import Path;"
                     "time.sleep(.7);(Path(sys.argv[1])/sys.argv[2]).write_text('escaped')")
            parent = ("import subprocess,sys;subprocess.Popen([sys.executable,'-c',"
                      + repr(child) + "," + repr(str(root)) + ",sys.argv[1]])")
            worker = Worker({
                "node_id": "host-A", "physical_host_id": "physical-A",
                "workdir": str(root / "worker"),
                "contract_path": str(contract),
                "repositories": {"fixture": str(repo)},
                "harnesses": {"fixture": {
                    "command": [sys.executable, "-c", parent, "{job_id}"]}},
                "max_job_seconds": 10, "clone_timeout_seconds": 20,
                "max_concurrent": 1, "max_queued": 5
            })
            try:
                for i in range(10):
                    job_id = f"rapid-{i}"
                    request = {
                        "job_id": job_id, "task_id": "FIXTURE",
                        "repository": "fixture", "commit_sha": commit,
                        "role": "blind-review", "harness": "fixture", "model": "mock",
                        "contract_sha256": sha256_bytes(contract.read_bytes())
                    }
                    worker.submit(request)
                    stop = time.monotonic() + 12
                    while time.monotonic() < stop:
                        row = worker.store.get(job_id)
                        if row["state"] in ("COMPLETED", "FAILED", "CANCELLED",
                                            "INTERRUPTED", "TIMED_OUT"):
                            break
                        time.sleep(.02)
                    self.assertEqual(row["state"], "FAILED", row.get("error"))
                time.sleep(1.1)
                leaked = sorted(p.name for p in root.glob("rapid-*")
                                if p.is_file())
                self.assertEqual(leaked, [], "A descendant escaped its assigned Job Object")
            finally:
                worker.shutdown()
                worker.store.close()


if __name__ == "__main__":
    unittest.main()
