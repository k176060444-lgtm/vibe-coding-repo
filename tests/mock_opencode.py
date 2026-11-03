"""Fake OpenCode JSONL stream. Not a real model review."""
import json
import sys

job_id, commit = sys.argv[1:3]
print(json.dumps({"type": "step_start", "part": {"type": "step-start"}}))
print(json.dumps({"type": "text", "part": {"type": "text", "text": json.dumps({
    "job_id": job_id,
    "commit_sha": commit,
    "role": "blind-review",
    "verdict": "REQUEST_CHANGES",
    "summary": "MOCK ONLY - found one fixture issue",
    "findings": [{"severity": "IMPORTANT", "location": "hello.py:1", "description": "Fixture finding"}],
})}}))
print(json.dumps({"type": "step_finish", "part": {"type": "step-finish", "reason": "stop"}}))
