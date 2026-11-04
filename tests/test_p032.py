"""P0.3.2 regressions for pre-dispatch compatibility and HTTP body integrity."""
from __future__ import annotations

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

from blindreview.coordinator import Coordinator
from blindreview.http_client import ReviewClient, TransportError
from blindreview.worker import _WindowsLaunchGate
from test_pipeline import synthetic_host_fingerprint


class HTTPBodyIntegrity(unittest.TestCase):
    def _client_for(self, body: bytes, content_length: str | None):
        class Response(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                if content_length is not None:
                    self.send_header("Content-Length", content_length)
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
                self.close_connection = True
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Response)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, ReviewClient(f"http://127.0.0.1:{server.server_port}",
                                    "synthetic-http-token", timeout=2)

    def test_truncated_but_valid_json_is_rejected(self):
        server, client = self._client_for(b"{}", "50")
        try:
            with self.assertRaises(TransportError) as ctx:
                client.status("truncated")
            self.assertIn("Incomplete response body", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()

    def test_missing_content_length_is_rejected(self):
        server, client = self._client_for(b"{}", None)
        try:
            with self.assertRaises(TransportError) as ctx:
                client.status("missing-length")
            self.assertIn("Missing Content-Length", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()


class PreDispatchCompatibility(unittest.TestCase):
    def test_legacy_worker_is_rejected_before_any_peer_receives_submit(self):
        calls = {"legacy_submit": 0}

        class LegacyP02Worker(BaseHTTPRequestHandler):
            def do_GET(self):
                # P0.2/P0.3.1 has no /v1/version endpoint.
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_POST(self):
                calls["legacy_submit"] += 1
                self.send_response(201)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            def log_message(self, *args):
                pass

        legacy_server = ThreadingHTTPServer(("127.0.0.1", 0), LegacyP02Worker)
        threading.Thread(target=legacy_server.serve_forever, daemon=True).start()

        class CurrentPeer:
            def __init__(self):
                self.submit_calls = 0
            def version(self):
                return {"protocol_version": 3, "worker_version": "0.3.2",
                        "capabilities": ["preflight-before-submit", "host-fingerprint"],
                        "node_id": "A", "physical_host_id": "physical-A",
                        "host_fingerprint": synthetic_host_fingerprint("A")}
            def submit(self, request):
                self.submit_calls += 1
                raise AssertionError("Coordinator dispatched before all-peer preflight")
            def status(self, job_id):
                raise AssertionError("Unexpected status request before dispatch")
            def report(self, job_id):
                raise AssertionError("Unexpected report request before dispatch")
            def cancel(self, job_id):
                raise AssertionError("NOT_SUBMITTED jobs must not be remotely cancelled")

        modern = CurrentPeer()
        token = "legacy-preflight-token-123456789"
        legacy = ReviewClient(f"http://127.0.0.1:{legacy_server.server_port}", token, timeout=2)
        nodes = [
            {"id": "A", "url": "http://a.invalid", "token_env": "A_TOKEN",
             "harness": "mock", "model": "mock", "physical_host_id": "physical-A",
             "host_fingerprint": synthetic_host_fingerprint("A")},
            {"id": "B", "url": f"http://127.0.0.1:{legacy_server.server_port}", "token_env": "B_TOKEN",
             "harness": "mock", "model": "mock", "physical_host_id": "physical-B",
             "host_fingerprint": synthetic_host_fingerprint("B")},
        ]
        config = {"task_id": "PREFLIGHT", "repository": "fixture", "commit_sha": "a" * 40,
                  "contract_sha256": "b" * 64, "nodes": nodes, "poll_interval_seconds": 1,
                  "third_grace_seconds": 0, "overall_deadline_seconds": 30}
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = Coordinator(config, Path(tmp), client_factory=lambda node:
                                      modern if node["id"] == "A" else legacy)
            try:
                coordinator.initialize()
                self.assertEqual(coordinator.step(), "FAILED_PROTOCOL_PREFLIGHT")
                self.assertEqual(modern.submit_calls, 0)
                self.assertEqual(calls["legacy_submit"], 0)
                self.assertEqual(coordinator.state["protocol_preflight"]["status"], "REJECTED")
                self.assertIn("HTTP status 404", coordinator.state["jobs"]["B"]["last_error"])
                self.assertFalse(coordinator.state["accepted_nodes"])
            finally:
                coordinator.close()
        legacy_server.shutdown()
        legacy_server.server_close()


@unittest.skipUnless(os.name == "nt", "Parent process handle behavior requires native Windows")
class WindowsLauncherParentLifetime(unittest.TestCase):
    def test_launcher_exits_when_worker_dies_before_gate_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "must-not-run.txt"
            spec = root / "approved-launch.json"
            spec.write_text(json.dumps({"argv": [
                sys.executable, "-c",
                "from pathlib import Path;Path(" + repr(str(marker)) + ").write_text('started')"
            ]}), encoding="utf-8")
            gate = _WindowsLaunchGate()
            parent = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(10)"])
            launcher_path = Path(__file__).resolve().parents[1] / "blindreview" / "_win_launcher.py"
            launcher = None
            try:
                launcher = subprocess.Popen([
                    sys.executable, "-I", "-u", str(launcher_path),
                    str(spec), gate.name, str(parent.pid)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Give the launcher time to open the event and parent handles.
                time.sleep(0.5)
                parent.terminate()
                parent.wait(timeout=3)
                self.assertEqual(launcher.wait(timeout=3), 75)
                self.assertFalse(marker.exists(), "Harness ran after Worker exited before gate release")
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=3)
                if launcher is not None and launcher.poll() is None:
                    launcher.kill()
                    launcher.wait(timeout=3)
                gate.close()


if __name__ == "__main__":
    unittest.main()
