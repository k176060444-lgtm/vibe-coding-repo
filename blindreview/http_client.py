"""Short-lived authenticated HTTP requests with explicit whole-call deadline.

Only configured worker origins are contacted; redirects are never followed.
"""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from typing import Any
from urllib.parse import urlsplit


class TransportError(Exception):
    pass


class ReviewClient:
    def __init__(self, base_url: str, token: str, timeout: float = 8) -> None:
        url = urlsplit(base_url)
        if (url.scheme not in ("http", "https") or not url.hostname or
                url.username or url.password or url.query or url.fragment or
                url.path not in ("", "/")):
            raise ValueError("Worker URL must be a bare http(s) origin without credentials")
        if not token or any(ch in token for ch in "\r\n"):
            raise ValueError("Invalid worker token")
        if not (0 < float(timeout) <= 120):
            raise ValueError("HTTP timeout must be in (0,120] seconds")
        self.base_url = base_url.rstrip("/")
        self._parsed = url
        self.token = token
        self.timeout = float(timeout)

    def _call(self, method: str, path: str, obj: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8") if obj is not None else None
        timeout = self.timeout
        connection_type = http.client.HTTPSConnection if self._parsed.scheme == "https" else http.client.HTTPConnection
        conn = connection_type(self._parsed.hostname, self._parsed.port, timeout=timeout)
        expired = threading.Event()
        finished = threading.Event()
        live_socket = [None]  # retain even if HTTPResponse takes ownership

        def abort() -> None:
            if finished.is_set():
                return
            expired.set()
            # close() alone does not always interrupt another thread's
            # buffered HTTP header read. shutdown() on the socket does.
            try:
                sock = live_socket[0] if live_socket[0] is not None else conn.sock
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
            except (OSError, ValueError):
                pass
            try:
                conn.close()
            except OSError:
                pass

        watchdog = threading.Timer(timeout, abort)
        watchdog.daemon = True
        started = time.monotonic()
        watchdog.start()
        try:
            conn.request(method, path, body=data, headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close"})
            live_socket[0] = conn.sock
            response = conn.getresponse()
            if response.status < 200 or response.status >= 300:
                raise TransportError(f"HTTP status {response.status}; redirects are forbidden")
            result_bytes = bytearray()
            while True:
                if expired.is_set() or time.monotonic() - started >= timeout:
                    raise TransportError("Whole-request deadline exceeded")
                chunk = response.read(4096)
                if not chunk:
                    break
                result_bytes.extend(chunk)
                if len(result_bytes) > 2 * 1024 * 1024:
                    raise TransportError("Response too large")
            if expired.is_set() or time.monotonic() - started >= timeout:
                raise TransportError("Whole-request deadline exceeded")
            result = json.loads(result_bytes)
            if not isinstance(result, dict):
                raise TransportError("Invalid response type")
            return result
        except TransportError:
            raise
        except (http.client.HTTPException, OSError, TimeoutError, ValueError) as ex:
            raise TransportError(f"Request failed: {type(ex).__name__}: {ex}") from ex
        finally:
            finished.set()
            watchdog.cancel()
            conn.close()

    def submit(self, request: dict[str, str]) -> dict[str, Any]:
        return self._call("POST", "/v1/jobs", request)

    def status(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}")

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/jobs/{job_id}/cancel", {})

    def report(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}/report")
