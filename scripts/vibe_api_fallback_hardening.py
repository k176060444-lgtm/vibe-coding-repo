#!/usr/bin/env python3
"""WO1 Hardening: API fallback with parent order validation for ext-auth-push.

This module adds API fallback capabilities to vibe_external_authorized_push.py
with strict parent order enforcement and changed_files anomaly detection.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GITHUB_API = "https://api.github.com"


def _api_call(token, method, url, data=None):
    """Make a GitHub API call via curl."""
    cmd = ["curl", "-s", "-X", method,
           "-H", f"Authorization: token {token}",
           "-H", "Content-Type: application/json", url]
    tmpf = None
    if data:
        tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmpf)
        tmpf.close()
        cmd.extend(["--data-binary", f"@{tmpf.name}"])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if tmpf:
        os.unlink(tmpf.name)
    try:
        return json.loads(proc.stdout)
    except:
        return {"raw": proc.stdout[:300], "stderr": proc.stderr[:200]}


def _upload_blob(token, repo, filepath):
    """Upload a file as a blob to the repo."""
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"encoding": "base64", "content": b64}, tmpf)
    tmpf.close()
    proc = subprocess.run(
        ["curl", "-s", "-X", "POST",
         "-H", f"Authorization: token {token}",
         "-H", "Content-Type: application/json",
         f"{GITHUB_API}/repos/{repo}/git/blobs",
         "--data-binary", f"@{tmpf.name}"],
        capture_output=True, text=True, timeout=60)
    os.unlink(tmpf.name)
    try:
        return json.loads(proc.stdout)
    except:
        return {"raw": proc.stdout[:300]}


def validate_parent_order(parents, expected_fork_head, expected_upstream):
    """Validate merge commit parent order.

    parent1 MUST be fork HEAD (PR head), parent2 MUST be upstream main.
    Returns (valid: bool, error: str|None).
    """
    if len(parents) < 2:
        return False, f"expected 2 parents, got {len(parents)}"
    if parents[0] != expected_fork_head:
        return False, f"parent1={parents[0][:12]}, expected fork HEAD={expected_fork_head[:12]}"
    if parents[1] != expected_upstream:
        return False, f"parent2={parents[1][:12]}, expected upstream={expected_upstream[:12]}"
    return True, None


def validate_changed_files_count(changed_files, expected_max=10):
    """Detect changed_files anomaly (e.g., 966 when expecting 2).

    Returns (normal: bool, warning: str|None).
    """
    if changed_files > expected_max:
        return False, (
            f"changed_files={changed_files} exceeds expected max={expected_max}. "
            f"Possible parent order issue or base SHA drift."
        )
    return True, None


def create_merge_commit_via_api(token, repo, tree_sha, fork_head_sha, upstream_sha, message):
    """Create a merge commit via Git Data API with CORRECT parent order.

    parent1 = fork_head_sha (PR head), parent2 = upstream_sha (base).
    Returns (success: bool, sha: str, error: str|None).
    """
    result = _api_call(token, "POST", f"/repos/{repo}/git/commits", {
        "message": message,
        "tree": tree_sha,
        "parents": [fork_head_sha, upstream_sha],  # CRITICAL: fork first
        "author": {"name": "VibeDev Worker", "email": "vibedev@local.invalid",
                    "date": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())},
        "committer": {"name": "VibeDev Worker", "email": "vibedev@local.invalid",
                       "date": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())},
    })

    sha = result.get("sha", "")
    if not sha or sha == "ERROR":
        return False, "", f"commit creation failed: {result.get('message', 'unknown')}"

    # Validate parent order on the created commit
    actual_parents = [p["sha"] for p in result.get("parents", [])]
    valid, err = validate_parent_order(actual_parents, fork_head_sha, upstream_sha)
    if not valid:
        return False, sha, f"parent order validation failed: {err}"

    return True, sha, None


def force_update_ref(token, repo, ref, new_sha, expected_current_sha):
    """Force update a ref with current_sha binding (force-with-lease equivalent).

    Returns (success: bool, error: str|None).
    """
    # First verify current ref matches expected
    current = _api_call(token, "GET", f"/repos/{repo}/git/{ref}")
    current_sha = current.get("object", {}).get("sha", "")
    if current_sha != expected_current_sha:
        return False, (
            f"current ref SHA={current_sha[:12]} != expected={expected_current_sha[:12]}. "
            f"Ref was modified by another process."
        )

    # Perform force update
    result = _api_call(token, "PATCH", f"/repos/{repo}/git/{ref}", {
        "sha": new_sha,
        "force": True,
    })

    if "message" in result and "not" in result.get("message", "").lower():
        return False, result["message"]

    return True, None


def execute_api_fallback(token, repo, branch, tree_sha, fork_head_sha,
                          upstream_sha, current_remote_sha, changed_files_expected=2):
    """Full API fallback push with all safety checks.

    Returns dict with execution details.
    """
    result = {
        "method": "api_fallback",
        "parent_order_enforced": True,
        "current_remote_sha_binding": True,
    }

    # Step 1: Verify remote SHA
    remote = _api_call(token, "GET",
                        f"/repos/{repo}/commits?sha={branch}&per_page=1")
    remote_sha = remote[0]["sha"] if isinstance(remote, list) and remote else ""
    result["remote_sha_before"] = remote_sha

    if remote_sha != current_remote_sha:
        result["success"] = False
        result["error"] = f"remote SHA mismatch: {remote_sha[:12]} != {current_remote_sha[:12]}"
        return result

    # Step 2: Create merge commit with correct parent order
    message = (
        "merge: upstream main into feat/qqbot-media-sending - resolve schema conflict\n\n"
        "Combines QQBot MEDIA [[as_document]] description with upstream\n"
        "react/unreact emoji/message_id fields in send_message_tool schema."
    )
    ok, sha, err = create_merge_commit_via_api(
        token, repo, tree_sha, fork_head_sha, upstream_sha, message)
    result["commit_sha"] = sha
    result["commit_ok"] = ok

    if not ok:
        result["success"] = False
        result["error"] = err
        return result

    # Step 3: Force update ref with current_sha binding
    ref = f"refs/heads/{branch}"
    ok, err = force_update_ref(token, repo, ref, sha, current_remote_sha)
    result["ref_update_ok"] = ok

    if not ok:
        result["success"] = False
        result["error"] = err
        return result

    # Step 4: Post-push verify
    time.sleep(2)
    post = _api_call(token, "GET",
                      f"/repos/{repo}/commits?sha={branch}&per_page=1")
    post_sha = post[0]["sha"] if isinstance(post, list) and post else ""
    result["remote_sha_after"] = post_sha
    result["remote_verify"] = post_sha == sha

    if not result["remote_verify"]:
        result["success"] = False
        result["error"] = f"post-push verify failed: {post_sha[:12]} != {sha[:12]}"
        return result

    # Step 5: Check changed_files via PR
    pr_info = _api_call(token, "GET", f"/repos/NousResearch/hermes-agent/pulls/40457")
    changed = pr_info.get("changed_files", 0)
    result["pr_changed_files"] = changed
    normal, warning = validate_changed_files_count(changed, expected_max=10)
    result["changed_files_normal"] = normal
    if not normal:
        result["changed_files_warning"] = warning

    result["success"] = True
    return result


# Self-test
if __name__ == "__main__":
    # Validate parent order check
    parents_ok = ["aaa", "bbb"]
    valid, _ = validate_parent_order(parents_ok, "aaa", "bbb")
    assert valid, "valid order should pass"

    parents_bad = ["bbb", "aaa"]
    valid, err = validate_parent_order(parents_bad, "aaa", "bbb")
    assert not valid, "wrong order should fail"
    assert "parent1" in err

    # Validate changed_files check
    normal, _ = validate_changed_files_count(2, 10)
    assert normal
    normal, warning = validate_changed_files_count(966, 10)
    assert not normal
    assert "966" in warning

    print("WO1 hardening self-tests: ALL PASS")
