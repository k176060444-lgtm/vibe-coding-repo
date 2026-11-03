from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from blindreview.common import ProtocolError, canonical_json, sha256_bytes, validate_report, validate_request
from blindreview.coordinator import Coordinator
from blindreview.http_client import ReviewClient
from blindreview.store import JobStore
from blindreview.worker import ReviewHandler, Worker

ROOT = Path(__file__).resolve().parent.parent


def make_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "hello.py").write_text("answer = 42\n")
    subprocess.run(["git", "-C", str(path), "add", "hello.py"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-m", "first", "-q"], check=True)
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"]).decode().strip()


class ContractsTest(unittest.TestCase):
    def setUp(self):
        self.request = {"job_id": "br-123", "task_id": "T-12", "repository": "test",
                        "commit_sha": "a" * 40, "role": "blind-review", "harness": "codex",
                        "model": "provider/model", "contract_sha256": "a" * 64}

    def test_request_rejects_injection_and_unknown_role(self):
        validate_request(self.request)
        with self.assertRaises(ProtocolError):
            validate_request({**self.request, "job_id": "../../bad"})
        with self.assertRaises(ProtocolError):
            validate_request({**self.request, "role": "worker"})
        with self.assertRaises(ProtocolError):
            validate_request({**self.request, "harness": "codex", "dangerous": True})

    def test_report_validation(self):
        report = {"job_id": "br-123", "commit_sha": "a"*40, "role": "blind-review", "verdict": "REQUEST_CHANGES",
                  "summary": "Found issue", "findings": [{"severity": "BLOCKER", "location": "hello.py:1", "description": "x"}]}
        report.update({key: self.request[key] for key in ("task_id", "contract_sha256", "harness", "model")})
        report.update({"node_id": "5bao", "physical_host_id": "host-5bao"})
        validate_report(report, self.request, "5bao", "host-5bao")
        with self.assertRaises(ProtocolError):
            validate_report({**report, "commit_sha": "b"*40}, self.request)
        with self.assertRaises(ProtocolError):
            validate_report({**report, "findings": [{"severity": "BLOCKER", "description": "missing location"}]}, self.request)


class StoreTest(unittest.TestCase):
    def test_idempotence_and_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            store = JobStore(Path(root) / "job.sqlite")
            job = {"job_id": "j1", "role": "blind-review"}
            self.assertTrue(store.submit(job)[1])
            self.assertFalse(store.submit(job)[1])
            with self.assertRaises(ProtocolError):
                store.submit({**job, "role": "worker"})
            store.transition("j1", "RUNNING", expected=("QUEUED",))
            store.close()
            restarted = JobStore(Path(root) / "job.sqlite")
            self.assertEqual(restarted.recover(), ["j1"])
            self.assertEqual(restarted.get("j1")["state"], "INTERRUPTED")
            self.assertEqual(restarted.recover(), [])
            restarted.close()


class WorkerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        repo = root / "repo"
        repo.mkdir()
        self.sha = make_repo(repo)
        contract = root / "contract.md"
        contract.write_text("Act as a read-only blind reviewer.", encoding="utf-8")
        self.request = {"job_id": "review-unique-1", "task_id": "TASK-1", "repository": "fixture",
                        "commit_sha": self.sha, "role": "blind-review", "harness": "fixture",
                        "model": "fixture-model", "contract_sha256": sha256_bytes(contract.read_bytes())}
        self.config = {"node_id": "5bao", "physical_host_id": "host-5bao", "workdir": str(root / "work"),
                       "contract_path": str(contract), "repositories": {"fixture": str(repo)},
                       "harnesses": {"fixture": {"command": [sys.executable, str(ROOT / "tests" / "mock_reviewer.py"),
                                                        "{report_path}", "{job_id}", "{commit_sha}", "{workspace}"]}},
                       "max_job_seconds": 12, "heartbeat_seconds": 1, "max_concurrent": 1}
        self.worker = Worker(self.config)
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.worker.shutdown()
        self.worker.store.close()
        self.tmp.cleanup()

    def wait(self, job_id, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.worker.store.get(job_id)
            if job["state"] in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
                return job
            time.sleep(0.04)
        self.fail("Worker did not finish in time")

    def test_worker_fixed_commit_report_and_idempotence(self):
        first, new = self.worker.submit(self.request)
        self.assertTrue(new)
        _, new = self.worker.submit(self.request)
        self.assertFalse(new)
        result = self.wait(self.request["job_id"])
        self.assertEqual(result["state"], "COMPLETED", result["error"])
        report_path = Path(self.config["workdir"]) / "jobs" / self.request["job_id"] / "report.json"
        self.assertEqual(report_path.read_text().count('"commit_sha"'), 1)
        self.assertEqual(hashlib.sha256(report_path.read_bytes()).hexdigest(), result["result_sha256"])
        self.assertEqual(json.loads(report_path.read_text())["commit_sha"], self.sha)

    def test_reject_contract_mismatch(self):
        with self.assertRaises(ProtocolError):
            self.worker.submit({**self.request, "contract_sha256": "b" * 64})

    def test_authenticated_http_job_lifecycle(self):
        token = "long-test-token-only-for-fixture-000001"
        handler = type("TestHandler", (ReviewHandler,), {"worker": self.worker, "token": token})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        port = self.server.server_port
        client = ReviewClient(f"http://127.0.0.1:{port}", token, timeout=2)
        self.assertIn(client.submit(self.request)["state"], ("QUEUED", "RUNNING"))
        self.wait(self.request["job_id"])
        status = client.status(self.request["job_id"])
        self.assertEqual(status["node_id"], "5bao")
        self.assertEqual(status["state"], "COMPLETED")
        self.assertEqual(client.report(self.request["job_id"])["report"]["verdict"], "APPROVE")
        self.assertEqual(client.submit(self.request)["state"], "COMPLETED")

    def test_opencode_jsonl_adapter(self):
        self.worker.harnesses["fixture"] = {
            "command": [sys.executable, str(ROOT / "tests" / "mock_opencode.py"),
                        "{job_id}", "{commit_sha}"],
            "report_mode": "opencode_jsonl"
        }
        self.worker.submit(self.request)
        result = self.wait(self.request["job_id"])
        self.assertEqual(result["state"], "COMPLETED", result["error"])
        path = Path(self.config["workdir"]) / "jobs" / self.request["job_id"] / "report.json"
        self.assertEqual(json.loads(path.read_text())["verdict"], "REQUEST_CHANGES")

    def test_cancel_running_review(self):
        self.config["harnesses"]["fixture"]["command"].append("10")
        self.worker.submit(self.request)
        deadline = time.monotonic() + 4
        while self.worker.store.get(self.request["job_id"])["state"] != "RUNNING" and time.monotonic() < deadline:
            time.sleep(.02)
        self.worker.store.cancel(self.request["job_id"])
        self.assertEqual(self.wait(self.request["job_id"])["state"], "CANCELLED")


class FakeClient:
    def __init__(self, node_id: str, clock):
        self.node_id = node_id
        self.clock = clock
        self.job = None
        self.finish_at = 0
        self.cancel_count = 0
        self.verdict = "APPROVE"

    def submit(self, request):
        self.job = request
        return self.status(request["job_id"])

    def status(self, job_id):
        state = "COMPLETED" if self.clock() >= self.finish_at else "RUNNING"
        report = self._report()
        return {"node_id": self.node_id, "physical_host_id": "host-" + self.node_id, "job_id": job_id, "state": state,
                "result_sha256": sha256_bytes((canonical_json(report) + "\n").encode()),
                "error": None}

    def _report(self):
        return {"job_id": self.job["job_id"], "task_id": self.job["task_id"],
                "contract_sha256": self.job["contract_sha256"], "harness": self.job["harness"],
                "model": self.job["model"], "node_id": self.node_id,
                "physical_host_id": "host-" + self.node_id, "role": "blind-review",
                "commit_sha": self.job["commit_sha"], "verdict": self.verdict,
                "summary": f"Examined {self.node_id}", "findings": []}

    def report(self, job_id):
        report = self._report()
        return {"job_id": job_id, "node_id": self.node_id, "physical_host_id": "host-" + self.node_id, "report": report,
                "report_sha256": sha256_bytes((canonical_json(report) + "\n").encode())}

    def cancel(self, job_id):
        self.cancel_count += 1
        return {"node_id": self.node_id, "physical_host_id": "host-" + self.node_id,
                "job_id": job_id, "state": "CANCELLED", "error": None}


class CoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 100_000.0
        self.clients = {}
        nodes = [{"id": name, "url": f"http://{name}.example", "harness": "codex", "model": "approved-model",
                  "token_env": "FAKE_TOKEN_" + name.upper(), "physical_host_id": "host-" + name} for name in ("5bao", "9bao", "rusty")]
        self.config = {"task_id": "TASK-1", "repository": "fixture", "commit_sha": "a"*40,
                       "contract_sha256": "b"*64, "nodes": nodes,
                       "poll_interval_seconds": 60, "third_grace_seconds": 600,
                       "overall_deadline_seconds": 2400}
        self.runner = Coordinator(self.config, Path(self.tmp.name), clock=lambda: self.now,
                                  sleep=lambda secs: None, client_factory=self._client)
        self.runner.initialize()

    def tearDown(self):
        self.runner.close()
        self.tmp.cleanup()

    def _client(self, node):
        client = FakeClient(node["id"], lambda: self.now)
        self.clients[node["id"]] = client
        return client

    def test_two_then_ten_minute_wait_and_cancel_third(self):
        self.clients["5bao"].finish_at = self.now
        self.clients["9bao"].finish_at = self.now + 60
        self.clients["rusty"].finish_at = self.now + 800
        self.assertIsNone(self.runner.step())
        self.now += 60
        self.assertIsNone(self.runner.step())
        self.assertEqual(self.runner.state["quorum_at"], self.now)
        self.now += 599
        self.assertIsNone(self.runner.step())
        self.now += 1
        self.assertEqual(self.runner.step(), "QUORUM_MET")
        self.assertEqual(set(self.runner.state["accepted_nodes"]), {"5bao", "9bao"})
        self.assertEqual(self.clients["rusty"].cancel_count, 1)
        self.assertEqual(json.loads((Path(self.tmp.name) / "summary.json").read_text())["result"], "QUORUM_MET")

    def test_third_completes_in_grace_period(self):
        self.clients["5bao"].finish_at = self.now
        self.clients["9bao"].finish_at = self.now
        self.clients["rusty"].finish_at = self.now + 240
        self.assertIsNone(self.runner.step())
        self.now += 240
        self.assertEqual(self.runner.step(), "QUORUM_MET")
        self.assertEqual(len(self.runner.state["accepted_nodes"]), 3)

    def test_one_reviewer_never_sufficient(self):
        self.clients["5bao"].finish_at = self.now
        self.clients["9bao"].finish_at = self.now + 9999
        self.clients["rusty"].finish_at = self.now + 9999
        self.assertIsNone(self.runner.step())
        self.now += 2400
        self.assertEqual(self.runner.step(), "FAILED_QUORUM_TIMEOUT")
        self.assertEqual(len(self.runner.state["accepted_nodes"]), 1)

    def test_restart_preserves_quorum_deadline(self):
        self.clients["5bao"].finish_at = self.now
        self.clients["9bao"].finish_at = self.now
        self.clients["rusty"].finish_at = self.now + 9999
        self.runner.step()
        old_quorum_at = self.runner.state["quorum_at"]
        self.runner.close()
        new = Coordinator(self.config, Path(self.tmp.name), clock=lambda: self.now,
                          sleep=lambda secs: None, client_factory=lambda node: self.clients[node["id"]])
        new.initialize(resume=True)
        self.assertEqual(new.state["quorum_at"], old_quorum_at)
        self.now += 601
        self.assertEqual(new.step(), "QUORUM_MET")
        new.close()

    def test_reconcile_cancel_after_interrupted_network(self):
        self.clients["5bao"].finish_at = self.now
        self.clients["9bao"].finish_at = self.now
        self.clients["rusty"].finish_at = self.now + 9999
        self.assertIsNone(self.runner.step())
        self.now += 600
        self.assertEqual(self.runner.step(), "QUORUM_MET")
        self.assertFalse(self.runner.reconcile_cancellations())
        self.assertEqual(self.clients["rusty"].cancel_count, 1)

    def test_changed_config_cannot_resume(self):
        self.runner.close()
        altered = dict(self.config, overall_deadline_seconds=2500)
        new = Coordinator(altered, Path(self.tmp.name), clock=lambda: self.now,
                          client_factory=lambda node: self.clients[node["id"]])
        with self.assertRaises(ValueError):
            new.initialize(resume=True)
        new.close()


if __name__ == "__main__":
    unittest.main()
