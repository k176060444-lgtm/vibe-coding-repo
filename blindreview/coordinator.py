"""Durable 2-of-3 blind-review orchestration with a bounded third-seat window."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .common import ProtocolError, TERMINAL, canonical_json, sha256_bytes, validate_report, validate_request
from .http_client import ReviewClient, TransportError


class Coordinator:
    def __init__(self, config: dict[str, Any], state_dir: Path,
                 *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 client_factory: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self.cfg = config
        self.clock = clock
        self.sleep = sleep
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "state.json"
        self.nodes = config["nodes"]
        if not (2 <= len(self.nodes) <= 3):
            raise ValueError("Configure two or three independent review nodes")
        ids = [node["id"] for node in self.nodes]
        urls = [node["url"].rstrip("/") for node in self.nodes]
        if len(set(ids)) != len(ids) or len(set(urls)) != len(urls):
            raise ValueError("Reviewer node IDs and endpoints must be distinct")
        self.poll_s = int(config.get("poll_interval_seconds", 60))
        self.grace_s = int(config.get("third_grace_seconds", 600))
        self.deadline_s = int(config.get("overall_deadline_seconds", 3600))
        if min(self.poll_s, self.deadline_s) <= 0 or self.grace_s < 0:
            raise ValueError("Invalid timing parameters")
        for node in self.nodes:
            for key in ("id", "url", "harness", "model", "token_env"):
                if not node.get(key):
                    raise ValueError(f"Missing node field {key}")
        self.config_sha = sha256_bytes(canonical_json(config).encode("utf-8"))
        self.clients = {}
        for node in self.nodes:
            if client_factory:
                self.clients[node["id"]] = client_factory(node)
            else:
                token = os.environ.get(node["token_env"], "")
                self.clients[node["id"]] = ReviewClient(node["url"], token,
                    timeout=float(config.get("request_timeout_seconds", 8)))
        self.state: dict[str, Any] = {}

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".staging-", suffix=".json")
        try:
            with os.fdopen(fd, "wb") as out:
                if os.name != "nt":
                    os.fchmod(out.fileno(), 0o600)
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def initialize(self, *, resume: bool = False) -> None:
        if resume:
            if not self.state_path.exists():
                raise ValueError("No coordinator state to resume")
            self.state = json.loads(self.state_path.read_text("utf-8"))
            if self.state["config_sha256"] != self.config_sha:
                raise ValueError("Task config changed; refusing unsafe resume")
            return
        if self.state_path.exists():
            raise ValueError("State already exists; use --resume or a fresh state directory")
        run_id = uuid.uuid4().hex[:20]
        jobs = {}
        for node in self.nodes:
            job_id = "br-" + run_id + "-" + node["id"]
            request = validate_request({
                "job_id": job_id,
                "task_id": self.cfg["task_id"],
                "repository": self.cfg["repository"],
                "commit_sha": self.cfg["commit_sha"],
                "role": "blind-review",
                "harness": node["harness"],
                "model": node["model"],
                "contract_sha256": self.cfg["contract_sha256"],
            })
            jobs[node["id"]] = {"request": request, "state": "NOT_SUBMITTED", "valid": False,
                                 "last_error": None, "last_seen_at": None,
                                 "report_sha256": None, "cancel_requested": False}
        self.state = {"schema_version": 1, "config_sha256": self.config_sha,
                      "run_id": run_id, "started_at": self.clock(), "quorum_at": None,
                      "finished_at": None, "result": None, "accepted_nodes": [], "jobs": jobs}
        self._save()

    def _save(self) -> None:
        self._atomic_json(self.state_path, self.state)

    def _receipt(self, node_id: str, payload: dict[str, Any]) -> None:
        if payload.get("node_id") != node_id:
            raise ProtocolError("Remote node ID mismatch")
        job = self.state["jobs"][node_id]
        if payload.get("job_id") != job["request"]["job_id"]:
            raise ProtocolError("Remote Job ID mismatch")
        state = payload.get("state")
        if state not in ("QUEUED", "RUNNING", *TERMINAL):
            raise ProtocolError("Invalid remote job state")
        job["state"] = state
        job["last_seen_at"] = self.clock()
        if payload.get("error"):
            job["last_error"] = str(payload["error"])[:1000]
        if state == "COMPLETED" and not job["valid"]:
            self._collect(node_id, payload)
        self._save()

    def _collect(self, node_id: str, status: dict[str, Any]) -> None:
        job = self.state["jobs"][node_id]
        payload = self.clients[node_id].report(job["request"]["job_id"])
        if payload.get("node_id") != node_id or payload.get("job_id") != job["request"]["job_id"]:
            raise ProtocolError("Report identity mismatch")
        report = validate_report(payload.get("report"), job["request"])
        expected = sha256_bytes((canonical_json(report) + "\n").encode("utf-8"))
        if not (expected == payload.get("report_sha256") == status.get("result_sha256")):
            raise ProtocolError("Report SHA256 mismatch")
        report_path = self.state_dir / "reports" / (node_id + ".json")
        self._atomic_json(report_path, report)
        job["report_sha256"] = expected
        job["valid"] = True
        job["accepted_at"] = self.clock()
        job["verdict"] = report["verdict"]

    def _query_one(self, node_id: str) -> None:
        job = self.state["jobs"][node_id]
        if job["valid"]:
            return
        client = self.clients[node_id]
        try:
            if job["state"] == "NOT_SUBMITTED":
                payload = client.submit(job["request"])
                self._receipt(node_id, payload)
            elif job["state"] not in TERMINAL or job["state"] == "COMPLETED":
                payload = client.status(job["request"]["job_id"])
                self._receipt(node_id, payload)
        except (TransportError, ProtocolError) as ex:
            job["last_error"] = str(ex)[:1000]
            self._save()

    def _cancel_one(self, node_id: str) -> None:
        job = self.state["jobs"][node_id]
        if job["valid"] or job["state"] in TERMINAL:
            return
        job["cancel_requested"] = True
        self._save()  # persist cancellation intent before remote side effect
        try:
            self._receipt(node_id, self.clients[node_id].cancel(job["request"]["job_id"]))
        except (TransportError, ProtocolError) as ex:
            job["last_error"] = "Cancellation unconfirmed: " + str(ex)[:950]
            self._save()

    def _finalize(self, result: str) -> str:
        self.state["result"] = result
        self.state["finished_at"] = self.clock()
        self._save()
        summary = {"result": result, "task_id": self.cfg["task_id"],
                   "commit_sha": self.cfg["commit_sha"], "run_id": self.state["run_id"],
                   "started_at": self.state["started_at"],
                   "quorum_at": self.state["quorum_at"],
                   "finished_at": self.state["finished_at"],
                   "accepted_nodes": self.state["accepted_nodes"],
                   "jobs": {key: {"state": item["state"], "valid": item["valid"],
                                   "verdict": item.get("verdict"),
                                   "report_sha256": item["report_sha256"],
                                   "last_error": item["last_error"],
                                   "cancel_requested": item["cancel_requested"]}
                            for key, item in self.state["jobs"].items()}}
        self._atomic_json(self.state_dir / "summary.json", summary)
        return result

    def step(self) -> str | None:
        """Perform one polling cycle. Uses wall-clock deadlines so restart cannot reset timers."""
        if self.state["result"] is not None:
            return self.state["result"]
        now = self.clock()
        if now - self.state["started_at"] >= self.deadline_s and self.state["quorum_at"] is None:
            for node_id in self.state["jobs"]:
                self._cancel_one(node_id)
            return self._finalize("FAILED_QUORUM_TIMEOUT")
        for node_id in self.state["jobs"]:
            # At/after the third-seat deadline, do not accept a late third report.
            if self.state["quorum_at"] is not None and now >= self.state["quorum_at"] + self.grace_s:
                if node_id not in self.state["accepted_nodes"]:
                    continue
            self._query_one(node_id)
        valid = sorted((node_id for node_id, job in self.state["jobs"].items() if job["valid"]),
                       key=lambda nid: (self.state["jobs"][nid].get("accepted_at", float("inf")), nid))
        if len(valid) >= 2 and self.state["quorum_at"] is None:
            self.state["quorum_at"] = self.clock()
            self._save()
        if self.state["quorum_at"] is not None:
            self.state["accepted_nodes"] = valid
            self._save()
            outstanding = [nid for nid, j in self.state["jobs"].items() if not j["valid"] and j["state"] not in TERMINAL]
            deadline = min(self.state["quorum_at"] + self.grace_s,
                           self.state["started_at"] + self.deadline_s)
            if len(valid) == len(self.nodes) or not outstanding or self.clock() >= deadline:
                for nid in outstanding:
                    self._cancel_one(nid)
                return self._finalize("QUORUM_MET" if len(valid) >= 2 else "FAILED_QUORUM")
            return None
        if all(job["state"] in TERMINAL for job in self.state["jobs"].values()):
            return self._finalize("FAILED_INSUFFICIENT_REVIEWERS")
        return None

    def reconcile_cancellations(self) -> list[str]:
        """Retry network-lost cancellation requests without restarting review jobs.

        Intended for a periodic post-run invocation when remote third-seat
        cancellation could not be confirmed during the original run.
        """
        if not self.state:
            raise ValueError("Initialize or resume coordinator state first")
        pending = []
        for node_id, job in self.state["jobs"].items():
            if not job["cancel_requested"] or job["state"] in TERMINAL:
                continue
            client = self.clients[node_id]
            try:
                status = client.status(job["request"]["job_id"])
                if status.get("node_id") != node_id or status.get("job_id") != job["request"]["job_id"]:
                    raise ProtocolError("Cancellation status identity mismatch")
                if status.get("state") in TERMINAL:
                    job["state"] = status["state"]
                    job["last_error"] = None
                    self._save()
                    continue
                self._receipt(node_id, client.cancel(job["request"]["job_id"]))
            except (TransportError, ProtocolError) as ex:
                job["last_error"] = "Cancellation unconfirmed: " + str(ex)[:950]
                self._save()
            if job["state"] not in TERMINAL:
                pending.append(node_id)
        return pending

    def run(self) -> str:
        while True:
            result = self.step()
            if result is not None:
                return result
            self.sleep(self.poll_s)
