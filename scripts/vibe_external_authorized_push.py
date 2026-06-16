#!/usr/bin/env python3
"""External Authorized Push Wrapper — controlled push to external repos.

Validates an approved external-repo push request, verifies remote branch
state, and executes push via a secure git credential helper that injects
the privileged token without exposing it in argv, env, or logs.

Usage:
    python3 scripts/vibe_external_authorized_push.py \\
        --approval-id <id> [--approval-dir <dir>] [--json] [--dry-run]

    python3 scripts/vibe_external_authorized_push.py \\
        --approval-file <path> [--json] [--dry-run]

    python3 scripts/vibe_external_authorized_push.py \\
        --token-preflight [--json]

    python3 scripts/vibe_external_authorized_push.py --list [--json]

Constraints:
    - Token ONLY read from standard token file (never from env).
    - Token NEVER output to stdout/stderr/log/report.
    - Token passed to git via temporary credential helper script (cleaned up).
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.0.0"

# ── Constants ──────────────────────────────────────────────────────────

DEFAULT_TOKEN_FILE = "/home/vibeworker/.vibedev/secrets/github_privileged_token"
DEFAULT_APPROVAL_DIR = os.path.expanduser("~/vibedev/privileged-approvals")
GITHUB_API = "https://api.github.com"

# Paths that are ALWAYS forbidden in changed_paths
FORBIDDEN_PATH_PREFIXES = [
    ".github/workflows/",
    ".github/actions/",
    "secrets/",
    ".env",
    "credentials",
    "ssh/",
    ".ssh/",
]

# Operations that are ALWAYS forbidden
FORBIDDEN_OPERATIONS = {"force_push", "delete_branch", "tag", "release", "deploy"}

# Non-standard token env vars that must NOT be set
NON_STANDARD_TOKEN_ENVS = [
    "GITHUB_PAT", "GITHUB_TOKEN", "GH_TOKEN",
    "GITHUB_AUTH_TOKEN", "GH_ENTERPRISE_TOKEN",
]


# ── Helpers ────────────────────────────────────────────────────────────

def _sha256_file(path):
    """SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _redact(text, token):
    """Replace token with [REDACTED] in text."""
    if token and token in text:
        return text.replace(token, "[REDACTED]")
    return text


def _load_approval(approval_dir, approval_id):
    """Load approval record by ID."""
    path = Path(approval_dir) / f"{approval_id}.json"
    if not path.exists():
        return None, f"Approval not found: {approval_id}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (json.JSONDecodeError, OSError) as e:
        return None, f"Failed to load {path}: {e}"


def _load_approval_file(filepath):
    """Load approval record from explicit file path."""
    p = Path(filepath)
    if not p.exists():
        return None, f"File not found: {filepath}"
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (json.JSONDecodeError, OSError) as e:
        return None, f"Failed to load {filepath}: {e}"


def _list_approvals(approval_dir):
    """List all approval records."""
    d = Path(approval_dir)
    if not d.exists():
        return []
    records = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                records.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return records


def _check_token_file(token_path):
    """Check token file exists with correct owner/mode/size.

    Returns (ok, details). NEVER returns token content.
    """
    details = {"path": token_path, "exists": False}
    p = Path(token_path)
    if not p.exists():
        details["error"] = "token file not found"
        return False, details
    details["exists"] = True

    try:
        st = p.stat()
    except OSError as e:
        details["error"] = f"stat failed: {e}"
        return False, details

    details["size"] = st.st_size
    if st.st_size <= 20:
        details["error"] = "token file too small (size <= 20)"
        return False, details

    mode = stat.S_IMODE(st.st_mode)
    details["mode"] = oct(mode)
    if mode != 0o600:
        details["error"] = f"token file mode {oct(mode)}, expected 0o600"
        return False, details

    try:
        import pwd
        owner_info = pwd.getpwuid(st.st_uid)
        details["owner"] = owner_info.pw_name
        if owner_info.pw_name != "vibeworker":
            details["error"] = (
                f"token file owner={owner_info.pw_name}, expected=vibeworker"
            )
            return False, details
    except (ImportError, KeyError):
        details["owner_check"] = "skipped (pwd unavailable)"

    details["error"] = None
    return True, details


def _check_non_standard_env():
    """Check if non-standard token env vars are set.

    Returns (clean: bool, violations: list).
    """
    violations = []
    for var in NON_STANDARD_TOKEN_ENVS:
        val = os.environ.get(var, "")
        if val:
            violations.append(f"{var} is set (length={len(val)})")
    return len(violations) == 0, violations


def _check_path_forbidden(path_str):
    """Check if a path matches forbidden prefixes."""
    lower = path_str.lower().replace("\\", "/")
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if lower.startswith(prefix.lower()):
            return True, f"forbidden path prefix: {prefix}"
    return False, None


def _verify_remote_branch_sha(repo, branch, expected_sha, token):
    """Verify remote branch SHA matches expected via GitHub API.

    Returns (match: bool, actual_sha: str, error: str|None).
    """
    # Parse owner/repo from full_name
    api_url = f"{GITHUB_API}/repos/{repo}/commits?sha={branch}&per_page=1"

    try:
        # Use curl with token in header (not in URL)
        proc = subprocess.run(
            [
                "curl", "-s", "-f",
                "-H", f"Authorization: token {token}",
                "-H", "Accept: application/vnd.github.v3+json",
                api_url,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return False, "", f"API request failed: rc={proc.returncode}"

        data = json.loads(proc.stdout)
        if isinstance(data, list) and data:
            actual_sha = data[0].get("sha", "")
            return actual_sha == expected_sha, actual_sha, None
        elif isinstance(data, dict):
            return False, "", f"API error: {data.get('message', 'unknown')}"
        else:
            return False, "", "unexpected API response"
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        return False, "", f"verification error: {e}"


# ── Validation ─────────────────────────────────────────────────────────

def _validate_approval(record):
    """Validate all constraints for an external authorized push.

    Returns (would_push: bool, blockers: list, warnings: list).
    """
    blockers = []
    warnings = []

    # 1. Required fields
    required = [
        "approval_id", "repo", "branch", "operation",
        "base_sha", "local_commit_sha", "changed_paths",
        "patch_sha256", "expires_at",
    ]
    missing = [f for f in required if not record.get(f)]
    if missing:
        blockers.append(f"missing required fields: {missing}")

    # 2. Operation must be 'push'
    op = record.get("operation", "")
    if op != "push":
        blockers.append(f"operation='{op}', expected='push'")

    # 3. Forbidden operations
    allowed_ops = record.get("allowed_operations", [])
    for fo in FORBIDDEN_OPERATIONS:
        if fo in allowed_ops or fo == op:
            blockers.append(f"forbidden operation: {fo}")

    # 4. Force push check
    if record.get("force_push", False):
        blockers.append("force_push=true (forbidden)")

    # 5. Delete branch check
    if record.get("delete_branch", False):
        blockers.append("delete_branch=true (forbidden)")

    # 6. Tag/release/deploy check
    for flag in ["tag", "release", "deploy"]:
        if record.get(flag, False):
            blockers.append(f"{flag}=true (forbidden)")

    # 7. Expiry check
    expires_at = record.get("expires_at")
    if expires_at:
        if isinstance(expires_at, (int, float)):
            if time.time() > expires_at:
                blockers.append(
                    f"approval expired (expires_at={expires_at}, now={int(time.time())})"
                )
        elif isinstance(expires_at, str):
            # ISO format check
            try:
                from datetime import datetime, timezone
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp:
                    blockers.append(f"approval expired ({expires_at})")
            except (ValueError, TypeError):
                warnings.append(f"cannot parse expires_at: {expires_at}")

    # 8. Changed paths forbidden check
    changed_paths = record.get("changed_paths", [])
    for cp in changed_paths:
        is_forbidden, reason = _check_path_forbidden(cp)
        if is_forbidden:
            blockers.append(f"changed_path '{cp}': {reason}")

    # 9. No merge PR
    if record.get("merge_pr", False):
        blockers.append("merge_pr=true (forbidden)")

    # 10. Allowed operations must include push
    if allowed_ops and "push" not in allowed_ops:
        blockers.append(f"allowed_operations does not include 'push': {allowed_ops}")

    # 11. Standard token source check
    token_source = record.get("token_source", "")
    if token_source and token_source != DEFAULT_TOKEN_FILE:
        blockers.append(
            f"non-standard token_source: {token_source} "
            f"(expected: {DEFAULT_TOKEN_FILE})"
        )

    would_push = len(blockers) == 0
    return would_push, blockers, warnings


# ── Push Execution ─────────────────────────────────────────────────────

def _create_credential_helper(token):
    """Create a temporary git credential helper script.

    Returns path to the helper script. Caller must clean up.
    """
    helper_dir = tempfile.mkdtemp(prefix="vibedev-ext-push-")
    helper_path = os.path.join(helper_dir, "git-cred-helper.sh")

    # The credential helper receives "protocol=https\nhost=github.com\n\n"
    # on stdin and must output "password=<token>\n"
    helper_content = f"""#!/bin/bash
# Temporary credential helper for external authorized push
# Auto-generated — cleaned up after push
echo "password={token}"
"""
    with open(helper_path, "w") as f:
        f.write(helper_content)
    os.chmod(helper_path, 0o700)

    return helper_path, helper_dir


def _execute_push(record, token_path, dry_run=False):
    """Execute external authorized push.

    Uses git credential helper for secure token injection.
    Token NEVER appears in argv, env, or output.

    Returns (success: bool, details: dict).
    """
    result = {
        "approval_id": record.get("approval_id"),
        "repo": record.get("repo"),
        "branch": record.get("branch"),
        "local_commit_sha": record.get("local_commit_sha"),
        "dry_run": dry_run,
    }

    # 1. Validate approval
    would_push, blockers, warnings = _validate_approval(record)
    result["would_push"] = would_push
    result["blockers"] = blockers
    result["warnings"] = warnings

    if not would_push:
        result["push_executed"] = False
        return False, result

    # 2. Check non-standard env
    env_clean, env_violations = _check_non_standard_env()
    result["non_standard_env_clean"] = env_clean
    if not env_clean:
        result["blockers"] = result.get("blockers", []) + [
            f"non-standard token env: {v}" for v in env_violations
        ]
        result["push_executed"] = False
        return False, result

    # 3. Token preflight
    token_ok, token_details = _check_token_file(token_path)
    result["token_preflight"] = {
        k: v for k, v in token_details.items() if k != "content"
    }
    if not token_ok:
        result["push_executed"] = False
        result["blockers"] = result.get("blockers", []) + [
            f"token preflight failed: {token_details.get('error')}"
        ]
        return False, result

    # 4. Read token (never output it)
    try:
        with open(token_path, "r") as f:
            token = f.read().strip()
    except OSError as e:
        result["push_executed"] = False
        result["blockers"] = result.get("blockers", []) + [
            f"token read failed: {e}"
        ]
        return False, result

    # 5. Verify remote branch SHA
    repo = record["repo"]
    branch = record["branch"]
    expected_sha = record.get("remote_branch_current_sha")

    if expected_sha:
        sha_match, actual_sha, sha_err = _verify_remote_branch_sha(
            repo, branch, expected_sha, token
        )
        result["remote_sha_expected"] = expected_sha
        result["remote_sha_actual"] = actual_sha
        result["remote_sha_match"] = sha_match
        if not sha_match:
            result["push_executed"] = False
            result["blockers"] = result.get("blockers", []) + [
                f"remote SHA mismatch: expected={expected_sha[:12]} "
                f"actual={actual_sha[:12] if actual_sha else 'unknown'}"
                f"{f' ({sha_err})' if sha_err else ''}"
            ]
            return False, result

    # 6. Dry-run: stop here
    if dry_run:
        result["push_executed"] = False
        result["dry_run"] = True
        local_sha = record["local_commit_sha"]
        result["push_preview"] = (
            f"git -C <worktree> push "
            f"https://<TOKEN>@github.com/{repo}.git "
            f"{local_sha}:refs/heads/{branch}"
        )
        result["push_command_safe"] = (
            f"git push "
            f"https://github.com/{repo}.git "
            f"{local_sha}:refs/heads/{branch} "
            f"(token via credential helper, not in URL)"
        )
        return True, result

    # 7. Execute real push via credential helper
    helper_path = None
    helper_dir = None
    try:
        helper_path, helper_dir = _create_credential_helper(token)

        push_url = f"https://github.com/{repo}.git"
        local_sha = record["local_commit_sha"]
        refspec = f"{local_sha}:refs/heads/{branch}"

        # Construct push command with credential helper
        # Token is in the helper script, NOT in argv or env
        git_env = os.environ.copy()
        # Remove any non-standard token env vars from the subprocess env
        for var in NON_STANDARD_TOKEN_ENVS:
            git_env.pop(var, None)

        push_cmd = [
            "git", "push",
            push_url,
            refspec,
            f"--receive-pack=git-receive-pack",
        ]

        # Use GIT_ASKPASS to provide credentials
        # GIT_ASKPASS is called with no args and must print the password
        git_env["GIT_ASKPASS"] = helper_path
        git_env["GIT_TERMINAL_PROMPT"] = "0"

        push_result = subprocess.run(
            push_cmd,
            capture_output=True, text=True, timeout=120,
            env=git_env,
        )

        result["push_executed"] = True
        result["push_rc"] = push_result.returncode

        # Redact token from output
        stderr_clean = _redact(push_result.stderr, token)
        stdout_clean = _redact(push_result.stdout, token)
        result["push_stderr"] = stderr_clean[:500]
        result["push_stdout"] = stdout_clean[:500]

        if push_result.returncode != 0:
            result["push_status"] = "push_failed"
            result["blockers"] = result.get("blockers", []) + [
                f"git push failed: rc={push_result.returncode}"
            ]
            return False, result

        result["push_status"] = "pushed"
        return True, result

    except subprocess.TimeoutExpired:
        result["push_executed"] = False
        result["push_status"] = "timeout"
        result["blockers"] = result.get("blockers", []) + ["push timed out (120s)"]
        return False, result
    except OSError as e:
        result["push_executed"] = False
        result["push_status"] = "error"
        result["blockers"] = result.get("blockers", []) + [f"push error: {e}"]
        return False, result
    finally:
        # ALWAYS clean up credential helper
        if helper_path and os.path.exists(helper_path):
            try:
                os.unlink(helper_path)
            except OSError:
                pass
        if helper_dir and os.path.exists(helper_dir):
            try:
                os.rmdir(helper_dir)
            except OSError:
                pass


# ── Commands ───────────────────────────────────────────────────────────

def _cmd_token_preflight(args):
    """Check token file without reading content."""
    token_path = args.token_file or DEFAULT_TOKEN_FILE
    ok, details = _check_token_file(token_path)
    env_clean, env_violations = _check_non_standard_env()
    return {
        "token_preflight": {k: v for k, v in details.items() if k != "content"},
        "ok": ok,
        "non_standard_env_clean": env_clean,
        "env_violations": env_violations,
    }, 0 if ok else 1


def _cmd_list(args):
    """List all approval records."""
    records = _list_approvals(args.approval_dir)
    results = []
    for r in records:
        would_push, blockers, warnings = _validate_approval(r)
        results.append({
            "approval_id": r.get("approval_id"),
            "repo": r.get("repo"),
            "branch": r.get("branch"),
            "operation": r.get("operation"),
            "status": r.get("status"),
            "would_push": would_push,
            "blockers": blockers,
            "expires_at": r.get("expires_at"),
        })
    return {
        "total": len(records),
        "valid_count": sum(1 for r in results if r["would_push"]),
        "blocked_count": sum(1 for r in results if not r["would_push"]),
        "approvals": results,
    }, 0


def _cmd_validate(args):
    """Validate an approval without executing push."""
    record, err = _load_approval(args.approval_dir, args.approval_id)
    if err:
        return {"error": err, "would_push": False}, 1

    would_push, blockers, warnings = _validate_approval(record)
    env_clean, env_violations = _check_non_standard_env()

    result = {
        "approval_id": record.get("approval_id"),
        "repo": record.get("repo"),
        "branch": record.get("branch"),
        "operation": record.get("operation"),
        "would_push": would_push,
        "would_read_token": would_push,
        "blockers": blockers,
        "warnings": warnings,
        "non_standard_env_clean": env_clean,
        "env_violations": env_violations,
        "changed_paths": record.get("changed_paths", []),
        "patch_sha256": record.get("patch_sha256"),
        "local_commit_sha": record.get("local_commit_sha"),
        "remote_branch_current_sha": record.get("remote_branch_current_sha"),
        "base_sha": record.get("base_sha"),
        "expires_at": record.get("expires_at"),
        "dry_run": True,
    }
    return result, 0 if would_push else 1


def _cmd_dry_run(args):
    """Dry-run push: validate + remote SHA check + preview."""
    record, err = _load_approval(args.approval_dir, args.approval_id)
    if err:
        return {"error": err, "would_push": False}, 1

    token_path = args.token_file or DEFAULT_TOKEN_FILE

    # Check non-standard env first
    env_clean, env_violations = _check_non_standard_env()
    if not env_clean:
        return {
            "error": "non-standard token env detected",
            "env_violations": env_violations,
            "would_push": False,
        }, 1

    success, result = _execute_push(record, token_path, dry_run=True)
    return result, 0 if success else 1


def _cmd_push(args):
    """Execute real push."""
    record, err = _load_approval(args.approval_dir, args.approval_id)
    if err:
        return {"error": err, "would_push": False}, 1

    token_path = args.token_file or DEFAULT_TOKEN_FILE
    success, result = _execute_push(record, token_path, dry_run=False)
    return result, 0 if success else 1


# ── CLI ────────────────────────────────────────────────────────────────

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_external_authorized_push",
        description="External Authorized Push Wrapper — controlled push to external repos",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}"
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json", help="JSON output"
    )
    parser.add_argument(
        "--compact", action="store_true", help="Compact single-line output"
    )
    parser.add_argument(
        "--approval-dir",
        default=DEFAULT_APPROVAL_DIR,
        help="Directory for approval records",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Path to privileged token file (default: standard path)",
    )

    sub = parser.add_subparsers(dest="command")

    for name in ["validate", "dry-run", "push"]:
        p = sub.add_parser(name)
        p.add_argument("--approval-id", required=True, help="Approval ID")

    sub.add_parser("token-preflight", help="Check token file")
    sub.add_parser("list", help="List approvals")

    return parser


def _format_compact(result):
    """Format as compact single-line."""
    if "error" in result:
        return f"EAP ERROR | {result['error']}"
    if result.get("push_executed"):
        status = result.get("push_status", "unknown")
        return (
            f"EAP {status.upper()} | "
            f"{result.get('repo')}:{result.get('branch')} | "
            f"rc={result.get('push_rc')}"
        )
    if result.get("would_push"):
        if result.get("dry_run"):
            return (
                f"EAP DRY-RUN OK | "
                f"{result.get('repo')}:{result.get('branch')} | "
                f"sha_match={result.get('remote_sha_match', '?')}"
            )
        return (
            f"EAP READY | "
            f"{result.get('repo')}:{result.get('branch')}"
        )
    blockers = result.get("blockers", [])
    return f"EAP BLOCKED | {blockers[0] if blockers else 'unknown'}"


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine command from subcommand or flags
    cmd = args.command
    if not cmd:
        if args.approval_id:
            cmd = "validate"
        else:
            parser.print_help()
            return 1

    dispatch = {
        "validate": _cmd_validate,
        "dry-run": _cmd_dry_run,
        "push": _cmd_push,
        "token-preflight": _cmd_token_preflight,
        "list": _cmd_list,
    }

    handler = dispatch.get(cmd)
    if not handler:
        parser.print_help()
        return 1

    result, rc = handler(args)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        print(_format_compact(result))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
        elif cmd == "list":
            print(f"Approvals: {result['total']} total, "
                  f"{result['valid_count']} valid, "
                  f"{result['blocked_count']} blocked")
            for a in result["approvals"]:
                icon = "+" if a["would_push"] else "x"
                print(f"  [{icon}] {a['approval_id']}: "
                      f"{a['repo']}:{a['branch']} ({a['operation']})")
        elif cmd == "token-preflight":
            ok = result.get("ok", False)
            print(f"Token preflight: {'OK' if ok else 'FAIL'}")
            for k, v in result["token_preflight"].items():
                if k != "content":
                    print(f"  {k}: {v}")
        else:
            if result.get("push_executed"):
                print(f"PUSHED: {result['repo']}:{result['branch']} "
                      f"(rc={result.get('push_rc')})")
            elif result.get("would_push") and result.get("dry_run"):
                print(f"DRY-RUN OK: {result['repo']}:{result['branch']}")
                print(f"  remote_sha_match: {result.get('remote_sha_match')}")
                print(f"  push_command_safe: {result.get('push_command_safe')}")
            elif result.get("would_push"):
                print(f"WOULD PUSH: {result['repo']}:{result['branch']}")
            else:
                print(f"BLOCKED: {result.get('approval_id', 'unknown')}")
                for b in result.get("blockers", []):
                    print(f"  - {b}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
