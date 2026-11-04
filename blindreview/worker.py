"""Small persistent remote reviewer service; no Hermes/A2A synchronous waits."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import socket
import sys
import uuid
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .common import JOB_ID, NAME, ProtocolError, TERMINAL, canonical_json, sha256_bytes, sha256_file, bind_worker_report, ensure_pattern, local_host_fingerprint, report_bytes, validate_request
from .store import JobStore


class _WindowsJob:
    """Windows kernel Job Object: descendants die even if the CLI parent exits.

    Assign after spawning, before processing output. Assignment failure is fatal:
    this worker must not report a successful review without process-tree control.
    """
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                       ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
            if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(proc._handle))):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        except BaseException:
            self.close()
            raise

    def terminate(self) -> None:
        import ctypes
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise OSError(ctypes.get_last_error(), "TerminateJobObject failed")

    def close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            self.kernel.CloseHandle(handle)


class _WindowsLaunchGate:
    """Named kernel event; never release the launcher before Job assignment."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                             wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.SetEvent.argtypes = [wintypes.HANDLE]
        self.kernel.SetEvent.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.name = "Local\\BlindReviewLaunch-" + uuid.uuid4().hex
        self.handle = self.kernel.CreateEventW(None, False, False, self.name)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateEventW failed")

    def release(self) -> None:
        import ctypes
        if not self.handle or not self.kernel.SetEvent(self.handle):
            raise OSError(ctypes.get_last_error(), "SetEvent failed")

    def close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            self.kernel.CloseHandle(handle)


class Worker:
    """One persistent worker; job identity and role bindings fail closed."""
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.node_id = ensure_pattern("node_id", config["node_id"], NAME)
        self.physical_host_id = ensure_pattern("physical_host_id", config["physical_host_id"], NAME)
        self.host_fingerprint = local_host_fingerprint()  # derived from OS, never from config
        self.root = Path(config["workdir"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._worker_lock = None
        self._acquire_data_lock()
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
        self.max_queued = int(config.get("max_queued", 50))
        self.max_prompt_bytes = int(config.get("max_prompt_bytes", 1024 * 1024))
        if any(x <= 0 for x in (self.max_seconds, self.clone_seconds, self.heartbeat_seconds,
                                self.max_log_bytes, self.capacity, self.max_queued, self.max_prompt_bytes)) or self.stall_warn_seconds < 0:
            raise ValueError("Invalid time/capacity/size limits")
        if not self.repositories or not self.harnesses:
            raise ValueError("Configure at least one trusted repository and harness")
        self.store = JobStore(self.root / "jobs.sqlite3")
        self.recovery_warnings: list[str] = []
        self._executor = ThreadPoolExecutor(max_workers=self.capacity, thread_name_prefix="review")
        self._futures: dict[str, Future] = {}
        self._thread_lock = threading.RLock()
        self._submit_lock = threading.RLock()
        self._stopping = threading.Event()
        self._running: dict[str, subprocess.Popen[bytes]] = {}
        self._windows_jobs: dict[int, _WindowsJob] = {}
        self._windows_launch_gates: dict[int, _WindowsLaunchGate] = {}
        self._process_lock = threading.Lock()
        self._started_recovered = False

    def _acquire_data_lock(self) -> None:
        path = self.root / ".worker.lock"
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
            raise ValueError("Worker data directory already has an active owner") from ex
        self._worker_lock = stream

    def _release_data_lock(self) -> None:
        stream, self._worker_lock = self._worker_lock, None
        if stream is None:
            return
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

    def start_recovered(self) -> None:
        """Only call once the service has validated credentials AND bound its port."""
        if self._started_recovered:
            return
        self._started_recovered = True
        self.recovery_warnings = self.store.recover()
        for job in self.store.unfinished():
            if job["state"] == "QUEUED":
                if not self._job_binding_ok(job["request"]):
                    self.store.transition(job["job_id"], "FAILED", expected=("QUEUED",),
                                          error="Queued job contract/harness/repository binding drift on startup")
                    continue
                try:
                    self.schedule(job["job_id"])
                except ProtocolError:
                    # A bounded queue may be resumed in batches by an operator.
                    break

    def _binding(self, request: dict[str, str]) -> dict[str, Any]:
        return {"contract_sha256": request["contract_sha256"],
                "repository": request["repository"],
                "source": str(self.repositories[request["repository"]]),
                "harness": request["harness"],
                "harness_config": self.harnesses[request["harness"]],
                "node_id": self.node_id, "physical_host_id": self.physical_host_id}

    def _job_binding_ok(self, request: dict[str, str]) -> bool:
        try:
            job_dir = self.root / "jobs" / request["job_id"]
            snapshot = (job_dir / "contract.snapshot").read_bytes()
            stored = json.loads((job_dir / "execution_binding.json").read_bytes())
            return (sha256_bytes(snapshot) == request["contract_sha256"] and
                    stored == self._binding(request) and
                    sha256_bytes(self.contract.read_bytes()) == request["contract_sha256"])
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def submit(self, raw: Any) -> tuple[dict[str, Any], bool]:
        request = validate_request(raw)
        if request["repository"] not in self.repositories or request["harness"] not in self.harnesses:
            raise ProtocolError("Unknown repository alias or harness")
        if request["contract_sha256"] != sha256_bytes(self.contract.read_bytes()):
            raise ProtocolError("Role contract SHA256 differs from installed contract")
        with self._submit_lock:
            old = self.store.get(request["job_id"])
            if old:
                if canonical_json(old["request"]) != canonical_json(request):
                    raise ProtocolError("Job ID already exists with a different request")
                return old, False
            with self._thread_lock:
                if len(self._futures) >= self.capacity + self.max_queued:
                    raise ProtocolError("Worker queue full")
            # Before journal submission write an immutable binding snapshot; on crash,
            # absent/incomplete snapshots always fail closed on recovery.
            job_dir = self.root / "jobs" / request["job_id"]
            job_dir.mkdir(parents=True, exist_ok=True)
            snapshot = self.contract.read_bytes()
            if sha256_bytes(snapshot) != request["contract_sha256"]:
                raise ProtocolError("Contract changed during submission")
            (job_dir / "contract.snapshot").write_bytes(snapshot)
            (job_dir / "execution_binding.json").write_bytes(report_bytes(self._binding(request)))
            job, created = self.store.submit(request)
            if created:
                self.schedule(request["job_id"])
            return job, created

    def schedule(self, job_id: str) -> None:
        with self._thread_lock:
            if job_id in self._futures or self._stopping.is_set():
                return
            if len(self._futures) >= self.capacity + self.max_queued:
                raise ProtocolError("Worker queue full")
            fut = self._executor.submit(self._run, job_id)
            self._futures[job_id] = fut
            fut.add_done_callback(lambda _: self._forget(job_id))

    def _forget(self, job_id: str) -> None:
        with self._thread_lock:
            self._futures.pop(job_id, None)
        # Schedule persisted queued work from a recovered backlog without
        # creating one thread per job.
        if not self._stopping.is_set():
            with self._thread_lock:
                pending = set(self._futures)
            for row in self.store.unfinished():
                if row["state"] == "QUEUED" and row["job_id"] not in pending:
                    try:
                        self.schedule(row["job_id"])
                    except ProtocolError:
                        break

    def _child_env(self) -> dict[str, str]:
        names = self.config.get("env_allowlist", ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"])
        if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
            raise ValueError("env_allowlist must be a list of environment variable names")
        forbidden = {str(self.config.get("token_env", "BLIND_REVIEW_WORKER_TOKEN")).casefold()}
        # Windows environment variable names are case-insensitive. Normalize before
        # comparing, and never forward the server authentication secret to a child.
        return {k: os.environ[k] for k in names
                if k in os.environ and k.casefold() not in forbidden}

    def _run(self, job_id: str) -> None:
        proc = None
        launch_gate = None
        try:
            jobrow = self.store.get(job_id)
            if not jobrow or jobrow["state"] != "QUEUED":
                return
            job = jobrow["request"]
            if not self._job_binding_ok(job):
                self.store.transition(job_id, "FAILED", expected=("QUEUED",),
                                      error="Contract/repository/harness binding mismatch before execution")
                return
            if self._stopping.is_set() or not self.store.transition(job_id, "RUNNING", expected=("QUEUED",)):
                return
            job_dir = self.root / "jobs" / job_id
            worktree = job_dir / "source"
            report_file = job_dir / "report.json"
            stdout_file = job_dir / "execution.log"
            source = str(self.repositories[job["repository"]])
            # The Git helper, hooks and configured filters must never inherit the
            # service authentication token either.
            git_env = self._child_env()
            clone = subprocess.run(["git", "clone", "--no-local", "--no-checkout", "--", source, str(worktree)],
                                   capture_output=True, timeout=self.clone_seconds, check=False, env=git_env)
            if clone.returncode:
                raise RuntimeError("Clone failed: " + clone.stderr.decode(errors="replace")[-700:])
            checkout = subprocess.run(["git", "-C", str(worktree), "checkout", "--detach", job["commit_sha"]],
                                      capture_output=True, timeout=self.clone_seconds, check=False, env=git_env)
            if checkout.returncode:
                raise RuntimeError("Requested Git commit unavailable: " + checkout.stderr.decode(errors="replace")[-500:])
            if self.store.get(job_id)["cancel_requested"]:
                self.store.transition(job_id, "CANCELLED", expected=("RUNNING",), error="Cancelled before harness")
                return
            verified = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], timeout=15, env=git_env).decode().strip()
            if verified != job["commit_sha"]:
                raise RuntimeError("Verified commit differs from request")
            contract = (job_dir / "contract.snapshot").read_bytes()
            if sha256_bytes(contract) != job["contract_sha256"]:
                raise ProtocolError("Contract snapshot changed before harness")
            prompt = contract.decode("utf-8") + ("\n\nREVIEW JOB (approved metadata):\n"
                + f"job_id: {job_id}\ntask_id: {job['task_id']}\ncommit_sha: {verified}\n"
                + f"role: {job['role']}\nrepository: {job['repository']}\n"
                + f"contract_sha256: {job['contract_sha256']}\nnode_id: {self.node_id}\n"
                + "Review only this checked-out code. Do not edit any files. "
                + "Return exactly one JSON object (no Markdown), with job_id, commit_sha, role, "
                + "verdict, summary and findings. Findings have severity, path:line location, description. "
                + "Do not fabricate evidence.\n")
            prompt_bytes = prompt.encode("utf-8")
            if len(prompt_bytes) > self.max_prompt_bytes:
                raise RuntimeError("Prompt exceeds max_prompt_bytes")
            prompt_file = job_dir / "prompt.txt"
            prompt_file.write_bytes(prompt_bytes)
            harness = self.harnesses[job["harness"]]
            vals = {"model": job["model"], "workspace": str(worktree), "report_path": str(report_file),
                    "prompt_path": str(prompt_file), "prompt_text": prompt, "commit_sha": verified, "job_id": job_id}
            command = [self._expand(arg, vals) for arg in harness["command"]]
            if not command or not all(isinstance(s, str) for s in command):
                raise RuntimeError("Invalid harness command")
            flags: dict[str, Any] = {"cwd": str(worktree),
                "stdin": subprocess.PIPE if harness.get("stdin_prompt", False) else subprocess.DEVNULL,
                "stderr": subprocess.STDOUT, "env": self._child_env(), "close_fds": True,
                "bufsize": 0 if harness.get("stdin_prompt", False) else -1}
            if os.name == "nt":
                # An ordinary Popen followed by AssignProcessToJobObject races
                # with child process creation. Launch a trusted, gated Python
                # wrapper: it cannot spawn the Harness before the Worker has
                # assigned the wrapper to the Job Object.
                launch_gate = _WindowsLaunchGate()
                launch_path = job_dir / "approved-launch.json"
                launch_path.write_bytes(report_bytes({"argv": command}))
                command = [sys.executable, "-I", "-u",
                           str(Path(__file__).with_name("_win_launcher.py")),
                           str(launch_path), launch_gate.name, str(os.getpid())]
                flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                flags["start_new_session"] = True
            started = time.monotonic()
            timed_out = cancelled = output_limited = False
            with stdout_file.open("wb") as output:
                flags["stdout"] = output
                proc = subprocess.Popen(command, **flags)
                with self._process_lock:
                    self._running[job_id] = proc
                if os.name == "nt":
                    with self._process_lock:
                        self._windows_launch_gates[proc.pid] = launch_gate
                    job_handle = _WindowsJob(proc)
                    with self._process_lock:
                        self._windows_jobs[proc.pid] = job_handle
                    # This is the only instruction that permits the trusted
                    # launcher to spawn any command (including grandchildren).
                    launch_gate.release()
                self.store.set_pid(job_id, proc.pid)
                if harness.get("stdin_prompt", False):
                    # Never write a large prompt on the monitoring thread.
                    def feed() -> None:
                        try:
                            remaining = memoryview(prompt_bytes)
                            while remaining:
                                n = proc.stdin.write(remaining)
                                if not n:
                                    break
                                remaining = remaining[n:]
                        except (BrokenPipeError, OSError, ValueError):
                            pass
                        finally:
                            try:
                                proc.stdin.close()
                            except (BrokenPipeError, OSError, ValueError):
                                pass
                    threading.Thread(target=feed, name="stdin-" + job_id, daemon=True).start()
                last_heartbeat, last_size = 0.0, 0
                while proc.poll() is None:
                    row = self.store.get(job_id)
                    if row["cancel_requested"] or self._stopping.is_set():
                        cancelled = True
                        self._terminate(proc)
                        break
                    if time.monotonic() - started >= self.max_seconds:
                        timed_out = True
                        self._terminate(proc)
                        break
                    size = stdout_file.stat().st_size
                    if size > self.max_log_bytes:
                        output_limited = True
                        self._terminate(proc)
                        break
                    if time.monotonic() - last_heartbeat >= self.heartbeat_seconds:
                        self.store.heartbeat(job_id, progress=size > last_size)
                        last_size = size
                        last_heartbeat = time.monotonic()
                    time.sleep(0.1)
                proc.wait(timeout=10)
            # Ensure all descendants are terminated before a terminal status;
            # root-process exit alone is not sufficient (e.g. detached CLI child).
            self._terminate(proc)
            if stdout_file.stat().st_size > self.max_log_bytes:
                output_limited = True
            if output_limited:
                raise RuntimeError("Execution log exceeded configured maximum")
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
                if stdout_file.stat().st_size > 1_000_000:
                    raise RuntimeError("Oversized stdout report")
                report_file.write_bytes(stdout_file.read_bytes())
            elif mode == "opencode_jsonl":
                last_report = None
                with stdout_file.open("r", encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        try:
                            event = json.loads(line)
                            if event.get("type") != "text":
                                continue
                            candidate = json.loads(event.get("part", {}).get("text", ""))
                            if isinstance(candidate, dict):
                                last_report = candidate
                        except (ValueError, AttributeError, TypeError):
                            continue
                if last_report is None:
                    raise RuntimeError("No valid JSON review in OpenCode text events")
                report_file.write_bytes(report_bytes(last_report))
            elif mode != "file":
                raise RuntimeError("Invalid report_mode")
            if not report_file.is_file() or report_file.stat().st_size > 1_000_000:
                raise RuntimeError("Missing or oversized structured report")
            if subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], timeout=10, env=git_env).decode().strip() != verified:
                raise RuntimeError("Harness changed reviewed HEAD")
            changed = subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain", "--ignored=matching", "--untracked-files=all"], timeout=15, env=git_env)
            if changed.strip():
                raise RuntimeError("Reviewer modified review worktree (including ignored files)")
            original = json.loads(report_file.read_bytes())
            report = bind_worker_report(original, job, self.node_id, self.physical_host_id)
            report_file.write_bytes(report_bytes(report))  # binary canonical LF on all OSes
            self.store.transition(job_id, "COMPLETED", expected=("RUNNING",), result_sha256=sha256_file(report_file))
        except Exception as ex:
            if proc is not None and proc.poll() is None:
                try:
                    self._terminate(proc)
                except Exception:
                    pass
            if proc is not None and proc.poll() is None:
                self.store.transition(job_id, "INTERRUPTED", expected=("RUNNING",),
                                      error="Orphan process not confirmed stopped; operator reconciliation required")
            else:
                self.store.transition(job_id, "FAILED", expected=("RUNNING", "QUEUED"),
                                      error=f"{type(ex).__name__}: {str(ex)[:1000]}")
        finally:
            if proc is None:
                if launch_gate is not None:
                    launch_gate.close()
            if proc is None or proc.poll() is not None:
                with self._process_lock:
                    self._running.pop(job_id, None)

    @staticmethod
    def _expand(arg: str, replacements: dict[str, str]) -> str:
        if not isinstance(arg, str):
            raise ValueError("Harness command elements must be strings")
        for key, value in replacements.items():
            arg = arg.replace("{" + key + "}", value)
        return arg

    def _terminate(self, proc: subprocess.Popen[bytes]) -> None:
        """Terminate the process tree, including after root-process exit."""
        if os.name == "nt":
            with self._process_lock:
                group = self._windows_jobs.pop(proc.pid, None)
                gate = self._windows_launch_gates.pop(proc.pid, None)
            try:
                if group is not None:
                    try:
                        group.terminate()
                    finally:
                        group.close()
                elif proc.poll() is None:
                    # The gated launcher has not been permitted to spawn a
                    # Harness unless Job assignment succeeded.
                    done = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                          capture_output=True, timeout=10, check=False)
                    if done.returncode and proc.poll() is None:
                        raise RuntimeError("taskkill failed; process tree status unknown")
                proc.wait(timeout=5)
            finally:
                if gate is not None:
                    gate.close()
            return
        # The process group may outlive its leader. Always target it, even
        # when the CLI returned zero and proc.poll() is already non-None.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)
        # Terminate descendants that survived their root process.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def shutdown(self) -> None:
        self._stopping.set()
        with self._process_lock:
            running = list(self._running.values())
        for proc in running:
            try:
                self._terminate(proc)
            except Exception:
                pass
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._release_data_lock()


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

    def _protocol(self) -> bool:
        # Old P0.2 coordinators do not send this header. Refuse their calls
        # rather than allowing mixed-version identity validation to be bypassed.
        if self.headers.get("X-Blind-Review-Protocol") != "4":
            self._json(426, {"error": "Incompatible P0 coordinator protocol",
                             "required_protocol": "4"})
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError as ex:
            raise ProtocolError("Invalid Content-Length") from ex
        if not (0 < n <= 32768):
            raise ProtocolError("Request size must be between 1 and 32768 bytes")
        value = json.loads(self.rfile.read(n).decode("utf-8"))
        if not isinstance(value, dict):
            raise ProtocolError("JSON request must be an object")
        return value

    def _parts(self) -> list[str]:
        path = urlsplit(self.path).path
        if urlsplit(self.path).query:
            return []
        return path.strip("/").split("/")

    def do_POST(self) -> None:
        if not self._auth() or not self._protocol():
            return
        try:
            parts = self._parts()
            if parts == ["v1", "jobs"]:
                job, created = self.worker.submit(self._body())
                self._json(201 if created else 200, self._status(job))
            elif len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "cancel" and JOB_ID.fullmatch(parts[2]):
                self.worker.store.cancel(parts[2])
                job = self.worker.store.get(parts[2])
                if job:
                    self._json(200, self._status(job))
                else:
                    # Cancel-before-submit tombstone: a delayed POST cannot
                    # later start the job after an ambiguous network failure.
                    self._json(200, self._cancelled_unknown(parts[2]))
            else:
                self._json(404, {"error": "Unknown endpoint"})
        except (ProtocolError, json.JSONDecodeError, UnicodeDecodeError) as ex:
            self._json(409 if "already exists" in str(ex) else 400, {"error": str(ex)})

    def do_GET(self) -> None:
        if not self._auth() or not self._protocol():
            return
        parts = self._parts()
        if parts == ["v1", "version"]:
            self._json(200, {
                "protocol_version": 4,
                "worker_version": "0.3.3",
                "capabilities": ["preflight-before-submit", "host-fingerprint", "cancel-tombstone"],
                "node_id": self.worker.node_id,
                "physical_host_id": self.worker.physical_host_id,
                "host_fingerprint": self.worker.host_fingerprint,
            })
            return
        if len(parts) < 3 or len(parts) > 4 or parts[:2] != ["v1", "jobs"] or not JOB_ID.fullmatch(parts[2]):
            self._json(404, {"error": "Unknown endpoint"})
            return
        job = self.worker.store.get(parts[2])
        if not job:
            if len(parts) == 3 and self.worker.store.is_tombstoned(parts[2]):
                self._json(200, self._cancelled_unknown(parts[2]))
            else:
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
                             "report_sha256": job["result_sha256"], "physical_host_id": self.worker.physical_host_id,
                             "host_fingerprint": self.worker.host_fingerprint, "protocol_version": 4,
                             "report": json.loads(path.read_text("utf-8"))})
        else:
            self._json(409, {"error": "Report not available"})

    def _cancelled_unknown(self, job_id: str) -> dict[str, Any]:
        return self._status({
            "job_id": job_id, "state": "CANCELLED",
            "created_at": None, "started_at": None, "finished_at": None,
            "heartbeat_at": None, "progress_at": None,
            "error": "Cancelled before job submission",
            "result_sha256": None, "pid": None, "cancel_requested": True,
        })

    def _status(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"node_id": self.worker.node_id, "physical_host_id": self.worker.physical_host_id,
                "host_fingerprint": self.worker.host_fingerprint, "protocol_version": 4,
                "job_id": job["job_id"],
                "suspected_stall": bool(job["state"] == "RUNNING" and
                    self.worker.stall_warn_seconds and job["progress_at"] is not None and
                    time.time() - job["progress_at"] >= self.worker.stall_warn_seconds),
                "state": job["state"], "created_at": job["created_at"],
                "started_at": job["started_at"], "finished_at": job["finished_at"],
                "heartbeat_at": job["heartbeat_at"], "progress_at": job["progress_at"],
                "error": job["error"], "result_sha256": job["result_sha256"], "pid": job["pid"],
                "cancel_requested": job["cancel_requested"]}


def serve(config: dict[str, Any]) -> None:
    token = os.environ.get(config["token_env"], "")
    if len(token) < 24:
        raise ValueError("Worker token environment variable must contain at least 24 characters")
    worker = Worker(config)
    handler = type("BoundReviewHandler", (ReviewHandler,), {"worker": worker, "token": token})
    host = config.get("listen", "127.0.0.1")
    port = int(config.get("port", 8765))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except Exception:
        worker.shutdown()
        worker.store.close()
        raise
    try:
        worker.start_recovered()
        print(f"Review worker {worker.node_id} listening on {host}:{port}", flush=True)
        if worker.recovery_warnings:
            print("Interrupted jobs require orphan-process inspection:", worker.recovery_warnings, flush=True)
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
        worker.shutdown()
        worker.store.close()
