"""HTTP client with no redirects and a whole-response monotonic deadline."""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

class TransportError(Exception):
    pass

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class ReviewClient:
    def __init__(self, base_url: str, token: str, timeout: float = 8) -> None:
        url = urlsplit(base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("Worker URL must be a bare http(s) origin without credentials")
        if not token or any(ch in token for ch in "\r\n"):
            raise ValueError("Invalid worker token")
        if not (0 < float(timeout) <= 120):
            raise ValueError("HTTP timeout must be in (0,120] seconds")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = float(timeout)
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _call(self, method: str, path: str, obj: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(obj, separators=(",", ":")).encode() if obj is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json"})
        stop_at = time.monotonic() + self.timeout
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                # Reading a byte at a time uses the buffered fp but checks an absolute
                # deadline between bytes. A drip-fed peer cannot restart the deadline.
                body = bytearray()
                while True:
                    remaining = stop_at - time.monotonic()
                    if remaining <= 0:
                        raise TransportError("Whole-response deadline exceeded")
                    sock = getattr(getattr(response.fp, "raw", None), "_sock", None)
                    if sock is not None:
                        sock.settimeout(max(0.001, remaining))
                    piece = response.read(1)
                    if not piece:
                        break
                    body.extend(piece)
                    if len(body) > 2 * 1024 * 1024:
                        raise TransportError("Response too large")
                if time.monotonic() > stop_at:
                    raise TransportError("Whole-response deadline exceeded")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise TransportError("Invalid response type")
                return result
        except TransportError:
            raise
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError,
                ValueError, OSError) as ex:
            raise TransportError(f"Request failed: {type(ex).__name__}: {ex}") from ex

    def submit(self, request: dict[str, str]) -> dict[str, Any]:
        return self._call("POST", "/v1/jobs", request)

    def status(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}")

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/jobs/{job_id}/cancel", {})

    def report(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}/report")
