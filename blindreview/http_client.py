"""Bounded standard-library HTTP transport; query failures are not job failures."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class TransportError(Exception):
    pass


class ReviewClient:
    def __init__(self, base_url: str, token: str, timeout: float = 8) -> None:
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError("Worker URL must use http(s)")
        if not token:
            raise ValueError("Missing worker token")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _call(self, method: str, path: str, obj: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(obj, separators=(",", ":")).encode() if obj is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise TransportError("Response too large")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise TransportError("Invalid response type")
                return result
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as ex:
            raise TransportError(f"Request failed: {type(ex).__name__}: {ex}") from ex

    def submit(self, request: dict[str, str]) -> dict[str, Any]:
        return self._call("POST", "/v1/jobs", request)

    def status(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}")

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/jobs/{job_id}/cancel", {})

    def report(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}/report")
