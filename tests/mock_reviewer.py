"""Fixture only. This is NOT an actual coding agent or usable blind review."""
import json
import sys
import time
from pathlib import Path

report_path, job_id, commit, workspace = sys.argv[1:5]
if len(sys.argv) > 5:
    time.sleep(float(sys.argv[5]))
assert (Path(workspace) / ".git").exists()
Path(report_path).write_text(json.dumps({
    "job_id": job_id, "commit_sha": commit, "role": "blind-review",
    "verdict": "APPROVE", "summary": "MOCK ONLY - does not constitute a review", "findings": [],
}), encoding="utf-8")
