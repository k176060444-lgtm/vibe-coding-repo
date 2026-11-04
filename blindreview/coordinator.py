"""Durable independent-review quorum. A quorum is NOT a release approval."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .common import (ProtocolError, TERMINAL, canonical_json, report_bytes, SHA256, ensure_pattern,
                     sha256_bytes, sha256_file, validate_report, validate_request)
from .http_client import ReviewClient, TransportError


class Coordinator:
    def __init__(self, config: dict[str, Any], state_dir: Path,
                 *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 client_factory: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self.cfg, self.clock, self.sleep = config, clock, sleep
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "state.json"
        self.nodes = config["nodes"]
        if not (2 <= len(self.nodes) <= 3):
            raise ValueError("Require two or three independent review nodes")
        for node in self.nodes:
            for key in ("id", "url", "harness", "model", "token_env", "physical_host_id", "host_fingerprint"):
                if not node.get(key):
                    raise ValueError(f"Missing node field {key}")
            ensure_pattern("host_fingerprint", node["host_fingerprint"], SHA256)
        for key, values in {
            "node ID": [n["id"] for n in self.nodes],
            "endpoint": [n["url"].rstrip("/") for n in self.nodes],
            "token environment": [n["token_env"] for n in self.nodes],
            "declared physical host": [n["physical_host_id"] for n in self.nodes],
            "pinned OS host fingerprint": [n["host_fingerprint"] for n in self.nodes],
        }.items():
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate {key} cannot count as independent reviewers")
        self.node_map = {n["id"]: n for n in self.nodes}
        self.poll_s = int(config.get("poll_interval_seconds", 60))
        self.grace_s = int(config.get("third_grace_seconds", 600))
        self.deadline_s = int(config.get("overall_deadline_seconds", 3600))
        if self.poll_s <= 0 or not (0 <= self.grace_s <= 600) or self.deadline_s <= 0:
            raise ValueError("Poll/deadline must be positive; third-seat grace must not exceed 600 seconds")
        self.config_sha = sha256_bytes(canonical_json(config).encode("utf-8"))
        self.clients = {}
        configured_tokens = []
        for node in self.nodes:
            if client_factory:
                self.clients[node["id"]] = client_factory(node)
            else:
                token = os.environ.get(node["token_env"], "")
                if len(token) < 24:
                    raise ValueError("Missing/weak review token for " + node["id"])
                configured_tokens.append(token)
                self.clients[node["id"]] = ReviewClient(node["url"], token,
                    timeout=float(config.get("request_timeout_seconds", 8)))
        if not client_factory and len(set(configured_tokens)) != len(configured_tokens):
            raise ValueError("Different enrolled physical nodes must use distinct authentication tokens")
        self.state: dict[str, Any] = {}
        self._lock_file = None

    def _lock(self) -> None:
        if self._lock_file is not None:
            return
        path = self.state_dir / ".coordinator.lock"
        stream = open(path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                if not stream.read(1):
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as ex:
            stream.close()
            raise ValueError("Coordinator state directory already has an active owner") from ex
        self._lock_file = stream

    def close(self) -> None:
        stream = self._lock_file
        if stream is None:
            return
        self._lock_file = None
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    @staticmethod
    def _atomic_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".staging-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                if os.name != "nt":
                    os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        Coordinator._atomic_bytes(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    def initialize(self, *, resume: bool = False) -> None:
        self._lock()
        try:
            self._initialize_locked(resume=resume)
        except BaseException:
            self.close()
            raise

    def _initialize_locked(self, *, resume: bool = False) -> None:
        if resume:
            if not self.state_path.exists():
                raise ValueError("No coordinator state to resume")
            self.state = json.loads(self.state_path.read_text("utf-8"))
            if self.state["config_sha256"] != self.config_sha:
                raise ValueError("Task config changed; refusing unsafe resume")
            self._verify_resume_reports()
            return
        if self.state_path.exists():
            raise ValueError("State already exists; use --resume or fresh directory")
        run_id = uuid.uuid4().hex[:20]
        jobs = {}
        for node in self.nodes:
            job_id = "br-" + run_id + "-" + node["id"]
            request = validate_request({
                "job_id": job_id, "task_id": self.cfg["task_id"],
                "repository": self.cfg["repository"], "commit_sha": self.cfg["commit_sha"],
                "role": "blind-review", "harness": node["harness"], "model": node["model"],
                "contract_sha256": self.cfg["contract_sha256"],
            })
            jobs[node["id"]] = {"request": request, "state": "NOT_SUBMITTED", "valid": False,
                                  "last_error": None, "last_seen_at": None,
                                  "report_sha256": None, "cancel_requested": False}
        self.state = {"schema_version": 2, "config_sha256": self.config_sha,
                      "run_id": run_id, "started_at": self.clock(), "max_observed_at": self.clock(), "quorum_at": None,
                      "finished_at": None, "result": None, "accepted_nodes": [], "jobs": jobs}
        self._save()

    def _save(self) -> None:
        self._atomic_json(self.state_path, self.state)

    def _now(self) -> float:
        """Reject wall-clock regression rather than lengthening a grace window."""
        now = float(self.clock())
        high = self.state.get("max_observed_at")
        if not math.isfinite(now) or (high is not None and now + 0.001 < high):
            raise ProtocolError("Clock moved backwards; reconciliation required before proceeding")
        self.state["max_observed_at"] = max(now, high if high is not None else now)
        return now

    def _valid_nodes(self) -> list[str]:
        return sorted((nid for nid, job in self.state["jobs"].items() if job["valid"]),
                      key=lambda nid: (self.state["jobs"][nid].get("accepted_at", float("inf")), nid))

    def _rebuild_quorum(self) -> None:
        accepted = self._valid_nodes()
        self.state["accepted_nodes"] = accepted
        if len(accepted) >= 2 and self.state["quorum_at"] is None:
            self.state["quorum_at"] = self.state["jobs"][accepted[1]]["accepted_at"]

    def _verify_resume_reports(self) -> None:
        # A receipt is the durable acceptance transaction: it includes the
        # verified report and original clock time in ONE atomic filesystem write.
        # state.json and reports/*.json are recoverable derived views.
        for nid, job in self.state["jobs"].items():
            path = self.state_dir / "reports" / (nid + ".json")
            receipt_path = self.state_dir / "receipts" / (nid + ".json")
            if receipt_path.is_file():
                receipt = json.loads(receipt_path.read_bytes())
                data = validate_report(receipt["report"], job["request"], nid,
                                       self.node_map[nid]["physical_host_id"])
                digest = sha256_bytes(report_bytes(data))
                accepted_at = receipt["accepted_at"]
                if (receipt.get("node_id") != nid or
                        receipt.get("host_fingerprint") != self.node_map[nid]["host_fingerprint"] or
                        receipt.get("report_sha256") != digest or
                        not isinstance(accepted_at, (float, int)) or
                        not math.isfinite(accepted_at) or
                        accepted_at >= self.state["started_at"] + self.deadline_s):
                    raise ProtocolError(f"Invalid durable acceptance receipt for {nid}")
                if job["valid"] and (job.get("report_sha256") != digest or
                                      job.get("accepted_at") != accepted_at):
                    raise ProtocolError(f"Report/receipt disagreement for {nid}")
                if path.exists() and path.read_bytes() != report_bytes(data):
                    raise ProtocolError(f"Persisted report has changed for {nid}")
                if not path.exists():
                    self._atomic_bytes(path, report_bytes(data))
                job.update({"valid": True, "accepted_at": accepted_at, "verdict": data["verdict"],
                            "report_sha256": digest, "host_fingerprint": receipt["host_fingerprint"],
                            "state": "COMPLETED"})
            elif job["valid"]:
                # Read-only compatibility for already completed P0.2 runs.
                if not path.is_file() or sha256_file(path) != job["report_sha256"]:
                    raise ProtocolError(f"Persisted report has changed or disappeared for {nid}")
                data = json.loads(path.read_bytes())
                validate_report(data, job["request"], nid, self.node_map[nid]["physical_host_id"])
                if report_bytes(data) != path.read_bytes():
                    raise ProtocolError("Persisted report is not canonical")
            if job["valid"] and job.get("host_fingerprint", self.node_map[nid]["host_fingerprint"]) != self.node_map[nid]["host_fingerprint"]:
                raise ProtocolError("Stored host identity conflicts with pinned enrollment")
        accepted = self._valid_nodes()
        if len({self.node_map[n]["host_fingerprint"] for n in accepted}) != len(accepted):
            raise ProtocolError("Duplicate host identity in accepted reports")
        if len(accepted) >= 3:
            second_time = self.state["jobs"][accepted[1]]["accepted_at"]
            third_time = self.state["jobs"][accepted[2]]["accepted_at"]
            if third_time >= min(self.state["started_at"] + self.deadline_s,
                                 second_time + self.grace_s):
                raise ProtocolError("Third-seat receipt beyond the authorized window")
        self._rebuild_quorum()
        self._save()
        if self.state["result"] is not None:
            self._write_summary()

    def _receipt(self, nid: str, payload: dict[str, Any], *, collect: bool = True) -> None:
        if not isinstance(payload, dict) or payload.get("node_id") != nid:
            raise ProtocolError("Remote node ID mismatch")
        if payload.get("physical_host_id") != self.node_map[nid]["physical_host_id"]:
            raise ProtocolError("Remote physical host declaration mismatch")
        fingerprint = payload.get("host_fingerprint")
        if fingerprint != self.node_map[nid]["host_fingerprint"]:
            raise ProtocolError("Remote OS identity does not match pinned host enrollment")
        if any(other != nid and row.get("valid") and
               self.node_map[other]["host_fingerprint"] == fingerprint
               for other, row in self.state["jobs"].items()):
            raise ProtocolError("Duplicate physical host identity")
        job = self.state["jobs"][nid]
        if payload.get("job_id") != job["request"]["job_id"]:
            raise ProtocolError("Remote Job ID mismatch")
        status = payload.get("state")
        if not isinstance(status, str) or status not in ("QUEUED", "RUNNING", *TERMINAL):
            raise ProtocolError("Invalid remote state")
        job["state"] = status
        job["host_fingerprint"] = fingerprint
        job["last_seen_at"] = self._now()
        if payload.get("error"):
            job["last_error"] = str(payload["error"])[:1000]
        if status == "COMPLETED" and not job["valid"] and collect:
            self._collect(nid, payload)
        self._save()

    def _collect(self, nid: str, status: dict[str, Any]) -> None:
        job = self.state["jobs"][nid]
        payload = self.clients[nid].report(job["request"]["job_id"])
        if not isinstance(payload, dict) or payload.get("node_id") != nid or payload.get("job_id") != job["request"]["job_id"]:
            raise ProtocolError("Report response identity mismatch")
        if payload.get("physical_host_id") != self.node_map[nid]["physical_host_id"]:
            raise ProtocolError("Report physical host declaration mismatch")
        if payload.get("host_fingerprint") != self.node_map[nid]["host_fingerprint"]:
            raise ProtocolError("Report served by unexpected OS identity")
        report = validate_report(payload.get("report"), job["request"], nid, self.node_map[nid]["physical_host_id"])
        digest = sha256_bytes(report_bytes(report))
        if digest != payload.get("report_sha256") or digest != status.get("result_sha256"):
            raise ProtocolError("Report SHA256 mismatch")
        now = self._now()
        absolute_deadline = self.state["started_at"] + self.deadline_s
        if now >= absolute_deadline:
            raise ProtocolError("Report arrived after absolute deadline")
        if self.state["quorum_at"] is not None and now >= self.state["quorum_at"] + self.grace_s:
            raise ProtocolError("Third-seat report arrived after grace deadline")
        # Persist the report AND its original acceptance timestamp in a single
        # crash-safe receipt before updating derived report/state files.
        self._atomic_json(self.state_dir / "receipts" / (nid + ".json"),
                          {"node_id": nid, "host_fingerprint": self.node_map[nid]["host_fingerprint"],
                           "accepted_at": now, "report_sha256": digest, "report": report})
        path = self.state_dir / "reports" / (nid + ".json")
        self._atomic_bytes(path, report_bytes(report))
        job["report_sha256"] = digest
        job["valid"] = True
        job["accepted_at"] = now
        job["host_fingerprint"] = self.node_map[nid]["host_fingerprint"]
        job["verdict"] = report["verdict"]
        self._rebuild_quorum()
        self._save()  # both the second acceptance and quorum_at in the same state write

    def _query_one(self, nid: str) -> None:
        job = self.state["jobs"][nid]
        if job["valid"]:
            return
        try:
            if job["state"] == "NOT_SUBMITTED":
                self._receipt(nid, self.clients[nid].submit(job["request"]))
            elif job["state"] not in TERMINAL or job["state"] == "COMPLETED":
                self._receipt(nid, self.clients[nid].status(job["request"]["job_id"]))
        except (TransportError, ProtocolError, ValueError, TypeError, KeyError) as ex:
            job["last_error"] = str(ex)[:1000]
            self._save()

    def _cancel_one(self, nid: str) -> None:
        job = self.state["jobs"][nid]
        if job["valid"] or job["state"] in TERMINAL:
            return
        if job["state"] == "NOT_SUBMITTED":
            job["state"] = "CANCELLED"
            job["last_error"] = "Stopped before dispatch"
            self._save()
            return
        job["cancel_requested"] = True
        self._save()
        try:
            self._receipt(nid, self.clients[nid].cancel(job["request"]["job_id"]), collect=False)
        except (TransportError, ProtocolError, ValueError, TypeError, KeyError) as ex:
            job["last_error"] = "Cancellation unconfirmed: " + str(ex)[:950]
            self._save()

    def _write_summary(self) -> None:
        s = self.state
        summary = {"result": s["result"], "task_id": self.cfg["task_id"],
                   "commit_sha": self.cfg["commit_sha"], "run_id": s["run_id"],
                   "started_at": s["started_at"], "quorum_at": s["quorum_at"],
                   "finished_at": s["finished_at"], "accepted_nodes": s["accepted_nodes"],
                   "note": "QUORUM_MET verifies report slots only, NOT technical APPROVE or release authorization",
                   "jobs": {nid: {"state": job["state"], "valid": job["valid"],
                                   "verdict": job.get("verdict"), "report_sha256": job["report_sha256"],
                                   "last_error": job["last_error"], "cancel_requested": job["cancel_requested"]}
                            for nid, job in s["jobs"].items()}}
        self._atomic_json(self.state_dir / "summary.json", summary)

    def _finalize(self, result: str) -> str:
        # No terminal outcome may abandon an outstanding remote job. Record
        # cancellation intent before any network request; reconcile can retry.
        for nid, row in self.state["jobs"].items():
            if not row["valid"] and row["state"] not in TERMINAL:
                self._cancel_one(nid)
        self._rebuild_quorum()
        self.state["result"] = result
        self.state["finished_at"] = self._now()
        self._save()
        self._write_summary()
        return result

    def step(self) -> str | None:
        if self.state["result"] is not None:
            self._write_summary()  # rebuild after crash between state and summary writes
            return self.state["result"]
        self._rebuild_quorum()
        if self.state["quorum_at"] is not None:
            self._save()
        absolute_deadline = self.state["started_at"] + self.deadline_s
        if self._now() >= absolute_deadline and self.state["quorum_at"] is None:
            for nid in self.state["jobs"]:
                self._cancel_one(nid)
            return self._finalize("FAILED_QUORUM_TIMEOUT")
        for nid in self.state["jobs"]:
            now = self._now()
            if now >= absolute_deadline:
                break
            if self.state["quorum_at"] is not None:
                if now >= self.state["quorum_at"] + self.grace_s:
                    break
                if nid in self.state["accepted_nodes"]:
                    continue
            client = self.clients[nid]
            if isinstance(client, ReviewClient):
                deadline = absolute_deadline
                if self.state["quorum_at"] is not None:
                    deadline = min(deadline, self.state["quorum_at"] + self.grace_s)
                client.timeout = max(.001, min(float(self.cfg.get("request_timeout_seconds", 8)), deadline - now))
            self._query_one(nid)
        accepted = self._valid_nodes()
        if self.state["quorum_at"] is not None:
            deadline = min(absolute_deadline, self.state["quorum_at"] + self.grace_s)
            outstanding = [nid for nid,j in self.state["jobs"].items()
                           if not j["valid"] and j["state"] not in TERMINAL]
            if len(accepted) == len(self.nodes) or self._now() >= deadline or not outstanding and all(
                j["state"] != "COMPLETED" or j["valid"] for j in self.state["jobs"].values()):
                for nid in outstanding:
                    self._cancel_one(nid)
                return self._finalize("QUORUM_MET")
            return None
        remaining = sum(1 for j in self.state["jobs"].values()
                        if not j["valid"] and (j["state"] not in TERMINAL or j["state"] == "COMPLETED"))
        if len(accepted) + remaining < 2:
            return self._finalize("FAILED_INSUFFICIENT_REVIEWERS")
        if self._now() >= absolute_deadline:
            for nid in self.state["jobs"]:
                self._cancel_one(nid)
            return self._finalize("FAILED_QUORUM_TIMEOUT")
        return None

    def reconcile_cancellations(self) -> list[str]:
        if not self.state:
            raise ValueError("Initialize or resume coordinator first")
        pending = []
        for nid, job in self.state["jobs"].items():
            if not job["cancel_requested"] or job["state"] in TERMINAL:
                continue
            try:
                status = self.clients[nid].status(job["request"]["job_id"])
                self._receipt(nid, status, collect=False)
                if job["state"] not in TERMINAL:
                    self._receipt(nid, self.clients[nid].cancel(job["request"]["job_id"]), collect=False)
            except (TransportError, ProtocolError, ValueError, TypeError, KeyError) as ex:
                job["last_error"] = "Cancellation unconfirmed: " + str(ex)[:950]
                self._save()
            if job["state"] not in TERMINAL:
                pending.append(nid)
        if self.state["result"] is not None:
            self._write_summary()
        return pending

    def run(self) -> str:
        try:
            while True:
                result = self.step()
                if result is not None:
                    return result
                absolute = self.state["started_at"] + self.deadline_s
                if self.state["quorum_at"] is not None:
                    absolute = min(absolute, self.state["quorum_at"] + self.grace_s)
                remaining = absolute - self._now()
                if remaining > 0:
                    self.sleep(min(self.poll_s, remaining))
        finally:
            self.close()
