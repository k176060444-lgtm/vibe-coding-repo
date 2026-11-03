"""Small persistent remote reviewer service; no Hermes/A2A synchronous waits."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .common import JOB_ID, ProtocolError, TERMINAL, canonical_json, sha256_bytes, sha256_file, validate_report, validate_request
from .store import JobStore


class Worker:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.node_id = str(config["node_id"])
        self.root = Path(config["workdir"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.contract = Path(config["contract_path"]).resolve()
        self.contract_bytes = self.contract.read_bytes()
        self.contract_sha256 = sha256_bytes(self.contract_bytes)
        self.repositories = config["repositories"]
        self.harnesses = config["harnesses"]
        self.max_seconds = int(config.get("max_job_seconds", 1800))
        self.clone_seconds = int(config.get("clone_timeout_seconds", 240))
        self.heartbeat_seconds = int(config.get("heartbeat_seconds", 60))
        self.stall_warn_seconds = int(config.get("stall_warn_seconds", 300))
        self.max_log_bytes = int(config.get("max_log_bytes", 20 * 1024 * 1024))
        self.capacity = int(config.get("max_concurrent", 1))
        if self.max_seconds <= 0 or self.heartbeat_seconds <= 0 or self.capacity <= 0 or self.stall_warn_seconds < 0 or self.max_log_bytes <= 0:
            raise ValueError("Invalid time/capacity limits")
        if not self.repositories or not self.harnesses:
            raise ValueError("Configure at least one trusted repository and harness")
        self.store = JobStore(self.root / "jobs.sqlite3")
        self.recovery_warnings = self.store.recover()
        self._semaphore = threading.Semaphore(self.capacity)
        self._threads: dict[str, threading.Thread] = {}
        self._thread_lock = threading.Lock()
        self._stopping = threading.Event()
        self._running: dict[str, subprocess.Popen[bytes]] = {}
        self._process_lock = threading.Lock()
        for job in self.store.unfinished():
            if job["state"] == "QUEUED":
                self.schedule(job["job_id"])

    def submit(self, raw: Any) -> tuple[dict[str, Any], bool]:
        request = validate_request(raw)
        if request["repository"] not in self.repositories:
            raise ProtocolError("Unknown repository alias")
        if request["harness"] not in self.harnesses:
            raise ProtocolError("Unapproved harness on worker")
        if request["contract_sha256"] != self.contract_sha256:
            raise ProtocolError("Role contract SHA256 differs from worker's installed contract")
        job, created = self.store.submit(request)
        if created:
            self.schedule(request["job_id"])
        return job, created

    def schedule(self, job_id: str) -> None:
        with self._thread_lock:
            if job_id in self._threads:
                return
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True,
                                      name=f"review-{job_id}")
            self._threads[job_id] = thread
            thread.start()

    def _run(self, job_id: str) -> None:
        try:
            with self._semaphore:
                if self._stopping.is_set():
                    return
                if not self.store.transition(job_id, "RUNNING", expected=("QUEUED",)):
                    return
                job = self.store.get(job_id)["request"]
                job_dir = self.root / "jobs" / job_id
                job_dir.mkdir(parents=True, exist_ok=True)
                worktree = job_dir / "source"
                report_file = job_dir / "report.json"
                stdout_file = job_dir / "execution.log"
                source = str(self.repositories[job["repository"]])
                # The caller provides a repository alias only; source comes from trusted local config.
                clone = subprocess.run(["git", "clone", "--no-checkout", "--", source, str(worktree)],
                                       capture_output=True, timeout=self.clone_seconds, check=False)
                if clone.returncode:
                    raise RuntimeError("Clone failed: " + clone.stderr.decode(errors="replace")[-700:])
                checkout = subprocess.run(["git", "-C", str(worktree), "checkout", "--detach", job["commit_sha"]],
                                          capture_output=True, timeout=self.clone_seconds, check=False)
                if checkout.returncode:
                    raise RuntimeError("Requested Git commit unavailable: " + checkout.stderr.decode(errors="replace")[-500:])
                if self.store.get(job_id)["cancel_requested"]:
                    self.store.transition(job_id, "CANCELLED", expected=("RUNNING",),
                                          error="Cancelled before harness start")
                    return
                verified = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"],
                                                   timeout=15).decode().strip()
                if verified != job["commit_sha"]:
                    raise RuntimeError("Verified Git commit differs from request")
                prompt_file = job_dir / "prompt.txt"
                prompt = self.contract_bytes.decode("utf-8") + ("\n\nREVIEW JOB (fixed metadata):\n"
                    + f"job_id: {job['job_id']}\ntask_id: {job['task_id']}\ncommit_sha: {verified}\n"
                    + f"role: {job['role']}\nrepository: {job['repository']}\n"
                    + "Review only this checked-out code. Do not edit source files. "
                    + "Return exactly one JSON object matching this schema, without Markdown fences: "
                    + '{"job_id":"...","commit_sha":"...","role":"blind-review",'
                    + '"verdict":"APPROVE|APPROVE_WITH_COMMENTS|REQUEST_CHANGES|NEEDS_SPECIALIST",'
                    + '"summary":"...","findings":[{"severity":"BLOCKER|IMPORTANT|QUESTION|NIT|OPTIONAL|FYI",'
                    + '"location":"path:line","description":"..."}]}'
                    + "\nDo not fabricate file locations or tests.\n")
                prompt_file.write_text(prompt, encoding="utf-8")
                harness = self.harnesses[job["harness"]]
                values = {"model": job["model"], "workspace": str(worktree),
                          "report_path": str(report_file), "prompt_path": str(prompt_file),
                          "prompt_text": prompt, "commit_sha": verified, "job_id": job_id}
                command = [self._expand(arg, values) for arg in harness["command"]]
                if not command or not all(isinstance(s, str) for s in command):
                    raise RuntimeError("Invalid harness command")
                stdin = subprocess.PIPE if harness.get("stdin_prompt", False) else subprocess.DEVNULL
                flags: dict[str, Any] = {"cwd": str(worktree), "stdin": stdin,
                                         "stdout": None, "stderr": subprocess.STDOUT}
                if os.name == "nt":
                    flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    flags["start_new_session"] = True
                started = time.monotonic()
                with stdout_file.open("wb") as output:
                    flags["stdout"] = output
                    proc = subprocess.Popen(command, **flags)
                    self.store.set_pid(job_id, proc.pid)
                    with self._process_lock:
                        self._running[job_id] = proc
                    if harness.get("stdin_prompt", False):
                        try:
                            proc.stdin.write(prompt.encode("utf-8"))
                            proc.stdin.close()
                        except BrokenPipeError:
                            pass
                    last_heartbeat = 0.0
                    last_size = 0
                    timed_out = False
                    cancelled = False
                    output_limited = False
                    try:
                        while proc.poll() is None:
                            record = self.store.get(job_id)
                            if record["cancel_requested"] or self._stopping.is_set():
                                cancelled = True
                                self._terminate(proc)
                                break
                            if time.monotonic() - started > self.max_seconds:
                                timed_out = True
                                self._terminate(proc)
                                break
                            if stdout_file.stat().st_size > self.max_log_bytes:
                                output_limited = True
                                self._terminate(proc)
                                break
                            if time.monotonic() - last_heartbeat >= self.heartbeat_seconds:
                                size = stdout_file.stat().st_size
                                # Observed log output is a progress hint, not proof of model activity.
                                self.store.heartbeat(job_id, progress=size > last_size)
                                last_size = size
                                last_heartbeat = time.monotonic()
                            time.sleep(0.5)
                        proc.wait(timeout=10)
                    finally:
                        with self._process_lock:
                            self._running.pop(job_id, None)
                if output_limited:
                    self.store.transition(job_id, "FAILED", expected=("RUNNING",),
                                          error="Execution log exceeded configured maximum")
                    return
                if cancelled:
                    self.store.transition(job_id, "CANCELLED", expected=("RUNNING",), error="Cancelled by coordinator")
                    return
                if timed_out:
                    self.store.transition(job_id, "TIMED_OUT", expected=("RUNNING",), error="Harness hard deadline exceeded")
                    return
                if proc.returncode:
                    raise RuntimeError(f"Harness exited with code {proc.returncode}; see execution.log")
                mode = harness.get("report_mode", "file")
                if mode == "stdout":
                    report_file.write_bytes(stdout_file.read_bytes())
                elif mode == "opencode_jsonl":
                    # OpenCode emits text events among tool/reasoning events. Accept only
                    # a full JSON object in one text event (usually the final response).
                    last_report = None
                    with stdout_file.open("r", encoding="utf-8", errors="replace") as stream:
                        for line in stream:
                            try:
                                event = json.loads(line)
                                if event.get("type") != "text":
                                    continue
                                text = event.get("part", {}).get("text", "")
                                candidate = json.loads(text)
                                if isinstance(candidate, dict):
                                    last_report = candidate
                            except (ValueError, AttributeError, TypeError):
                                continue
                    if last_report is None:
                        raise RuntimeError("No valid JSON review in OpenCode text events")
                    report_file.write_text(canonical_json(last_report) + "\n", encoding="utf-8")
                elif mode != "file":
                    raise RuntimeError("Invalid report_mode in worker config")
                if not report_file.is_file() or report_file.stat().st_size > 1_000_000:
                    raise RuntimeError("Missing or oversized structured review report")
                after_sha = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], timeout=10).decode().strip()
                if after_sha != verified:
                    raise RuntimeError("Harness changed reviewed commit HEAD")
                changed = subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"], timeout=15)
                if changed.strip():
                    raise RuntimeError("Reviewer modified source worktree (read-only contract violation)")
                report = validate_report(json.loads(report_file.read_text(encoding="utf-8")), job)
                report_file.write_text(canonical_json(report) + "\n", encoding="utf-8")
                self.store.transition(job_id, "COMPLETED", expected=("RUNNING",),
                                      result_sha256=sha256_file(report_file))
        except Exception as ex:
            self.store.transition(job_id, "FAILED", expected=("RUNNING",),
                                  error=f"{type(ex).__name__}: {str(ex)[:1000]}")
        finally:
            with self._thread_lock:
                self._threads.pop(job_id, None)

    @staticmethod
    def _expand(arg: str, replacements: dict[str, str]) -> str:
        if not isinstance(arg, str):
            raise ValueError("Each harness command element must be a string")
        for k, value in replacements.items():
            arg = arg.replace("{" + k + "}", value)
        return arg

    @staticmethod
    def _terminate(proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=False)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                proc.kill()
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=5)

    def shutdown(self) -> None:
        self._stopping.set()
        with self._process_lock:
            running = list(self._running.values())
        for process in running:
            self._terminate(process)
        with self._thread_lock:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout=15)


class ReviewHandler(BaseHTTPRequestHandler):
    worker: Worker
    token: str
    server_version = "BlindReviewWorker/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid logging tokens, request bodies, or URL values.
        pass

    def _json(self, code: int, body: dict[str, Any]) -> None:
        content = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _auth(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + self.token).encode()):
            self._json(401, {"error": "Unauthorized"})
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError as ex:
            raise ProtocolError("Invalid Content-Length") from ex
        if not (0 < n <= 32768):
            raise ProtocolError("Request size must be between 1 and 32768 bytes")
        value = json.loads(self.rfile.read(n))
        if not isinstance(value, dict):
            raise ProtocolError("JSON request must be an object")
        return value

    def _parts(self) -> list[str]:
        path = urlsplit(self.path).path
        if urlsplit(self.path).query:
            return []
        return path.strip("/").split("/")

    def do_POST(self) -> None:
        if not self._auth():
            return
        try:
            parts = self._parts()
            if parts == ["v1", "jobs"]:
                job, created = self.worker.submit(self._body())
                self._json(201 if created else 200, self._status(job))
            elif len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "cancel" and JOB_ID.fullmatch(parts[2]):
                self.worker.store.cancel(parts[2])
                job = self.worker.store.get(parts[2])
                self._json(200, self._status(job)) if job else self._json(404, {"error": "Unknown job"})
            else:
                self._json(404, {"error": "Unknown endpoint"})
        except (ProtocolError, json.JSONDecodeError) as ex:
            self._json(409 if "already exists" in str(ex) else 400, {"error": str(ex)})

    def do_GET(self) -> None:
        if not self._auth():
            return
        parts = self._parts()
        if len(parts) < 3 or len(parts) > 4 or parts[:2] != ["v1", "jobs"] or not JOB_ID.fullmatch(parts[2]):
            self._json(404, {"error": "Unknown endpoint"})
            return
        job = self.worker.store.get(parts[2])
        if not job:
            self._json(404, {"error": "Unknown job"})
            return
        if len(parts) == 3:
            self._json(200, self._status(job))
        elif parts[3] == "report" and job["state"] == "COMPLETED":
            path = self.worker.root / "jobs" / parts[2] / "report.json"
            if not path.exists() or sha256_file(path) != job["result_sha256"]:
                self._json(409, {"error": "Report missing or hash mismatch"})
                return
            self._json(200, {"node_id": self.worker.node_id, "job_id": parts[2],
                             "report_sha256": job["result_sha256"], "report": json.loads(path.read_text("utf-8"))})
        else:
            self._json(409, {"error": "Report not available"})

    def _status(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"node_id": self.worker.node_id, "job_id": job["job_id"],
                "suspected_stall": bool(job["state"] == "RUNNING" and
                    self.worker.stall_warn_seconds and job["progress_at"] is not None and
                    time.time() - job["progress_at"] >= self.worker.stall_warn_seconds),
                "state": job["state"], "created_at": job["created_at"],
                "started_at": job["started_at"], "finished_at": job["finished_at"],
                "heartbeat_at": job["heartbeat_at"], "progress_at": job["progress_at"],
                "error": job["error"], "result_sha256": job["result_sha256"], "pid": job["pid"],
                "cancel_requested": job["cancel_requested"]}


def serve(config: dict[str, Any]) -> None:
    worker = Worker(config)
    token = os.environ.get(config["token_env"], "")
    if len(token) < 24:
        raise ValueError("Worker token environment variable must contain at least 24 characters")
    handler = type("BoundReviewHandler", (ReviewHandler,), {"worker": worker, "token": token})
    host = config.get("listen", "127.0.0.1")
    port = int(config.get("port", 8765))
    server = ThreadingHTTPServer((host, port), handler)
    try:
        print(f"Review worker {worker.node_id} listening on {host}:{port}", flush=True)
        if worker.recovery_warnings:
            print("Interrupted jobs require orphan-process inspection:", worker.recovery_warnings, flush=True)
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
        worker.shutdown()
        worker.store.close()
