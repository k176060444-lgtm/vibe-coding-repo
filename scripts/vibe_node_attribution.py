#!/usr/bin/env python3
"""Node / Agent Attribution Report — per-node execution tracking.

Generates a structured attribution report showing which node (Windows
controller / Debian worker) performed each action in a work order or
batch execution.

Usage:
    from vibe_node_attribution import generate_attribution, format_attribution

    attribution = generate_attribution(
        controller_node="windows",
        execution_node="debian",
        transport="ssh",
        commands_on_windows=["dispatch job", "approve"],
        commands_on_debian=["git commit", "python smoke"],
        git_mutation_node="debian",
        token_access_node="debian",
        token_access_type="preflight",
        pr_operation_node="debian",
        failure_node=None,
        evidence_location="~/vibedev/jobs/<id>/",
    )
    print(format_attribution(attribution))
"""

VERSION = "1.0.0"

# Standard node names
NODE_WINDOWS = "windows"
NODE_DEBIAN = "debian"
NODE_NONE = "none"

# Standard transport names
TRANSPORT_SSH = "ssh"
TRANSPORT_SCP = "scp"
TRANSPORT_LOCAL = "local"
TRANSPORT_NONE = "none"
TRANSPORT_API = "github_api"


def generate_attribution(
    controller_node=NODE_WINDOWS,
    execution_node=NODE_DEBIAN,
    transport=TRANSPORT_SSH,
    commands_on_windows=None,
    commands_on_debian=None,
    git_mutation_node=NODE_DEBIAN,
    token_access_node=NODE_NONE,
    token_access_type="none",
    token_redacted=True,
    pr_operation_node=NODE_NONE,
    api_fallback_used=False,
    api_fallback_node=NODE_NONE,
    failure_node=None,
    failure_description=None,
    retry_node=None,
    evidence_location=None,
):
    """Generate an attribution dict.

    Returns dict with all 10 attribution fields.
    """
    return {
        "attribution_version": VERSION,
        "controller_node": controller_node,
        "execution_node": execution_node,
        "transport": transport,
        "commands_executed_on_windows": commands_on_windows or [],
        "commands_executed_on_debian": commands_on_debian or [],
        "git_mutation_node": git_mutation_node,
        "token_access_node": token_access_node,
        "token_access_type": token_access_type,
        "token_redacted": token_redacted,
        "pr_operation_node": pr_operation_node,
        "api_fallback_used": api_fallback_used,
        "api_fallback_node": api_fallback_node if api_fallback_used else NODE_NONE,
        "failure_or_retry_node": failure_node,
        "failure_description": failure_description,
        "retry_node": retry_node,
        "evidence_location": evidence_location,
    }


def format_attribution(attr):
    """Format attribution dict as human-readable text block."""
    lines = [
        "## Node / Agent Attribution",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| controller_node | {attr.get('controller_node', '?')} |",
        f"| execution_node | {attr.get('execution_node', '?')} |",
        f"| transport | {attr.get('transport', '?')} |",
        f"| git_mutation_node | {attr.get('git_mutation_node', '?')} |",
        f"| token_access_node | {attr.get('token_access_node', 'none')} |",
        f"| token_access_type | {attr.get('token_access_type', 'none')} |",
        f"| token_redacted | {attr.get('token_redacted', True)} |",
        f"| pr_operation_node | {attr.get('pr_operation_node', 'none')} |",
        f"| api_fallback_used | {attr.get('api_fallback_used', False)} |",
        f"| api_fallback_node | {attr.get('api_fallback_node', 'none')} |",
        f"| failure_or_retry_node | {attr.get('failure_or_retry_node') or 'none'} |",
        f"| evidence_location | {attr.get('evidence_location') or 'N/A'} |",
        "",
    ]

    win_cmds = attr.get("commands_executed_on_windows", [])
    deb_cmds = attr.get("commands_executed_on_debian", [])

    if win_cmds:
        lines.append("**Windows controller commands:**")
        for cmd in win_cmds:
            lines.append(f"- {cmd}")
        lines.append("")

    if deb_cmds:
        lines.append("**Debian worker commands:**")
        for cmd in deb_cmds:
            lines.append(f"- {cmd}")
        lines.append("")

    fail_desc = attr.get("failure_description")
    if fail_desc:
        lines.append(f"**Failure:** {fail_desc}")
        lines.append("")

    return "\n".join(lines)


def format_attribution_json(attr):
    """Return attribution as JSON-serializable dict (for --json output)."""
    return attr


def validate_attribution(attr):
    """Validate attribution has all required fields.

    Returns (valid: bool, errors: list).
    """
    errors = []
    required = [
        "controller_node", "execution_node", "transport",
        "git_mutation_node", "token_access_node",
    ]
    for field in required:
        if field not in attr:
            errors.append(f"missing field: {field}")

    # Token content must NOT appear anywhere
    import json
    serialized = json.dumps(attr)
    if "ghp_" in serialized or "github_pat_" in serialized or "Bearer" in serialized:
        errors.append("token content detected in attribution")

    return len(errors) == 0, errors


# Default attribution for PR #40457 workflow (for reference)
PR40457_ATTRIBUTION = generate_attribution(
    controller_node=NODE_WINDOWS,
    execution_node=NODE_DEBIAN,
    transport=f"{TRANSPORT_SSH}/{TRANSPORT_SCP}",
    commands_on_windows=[
        "receive user instruction via QQ",
        "generate work plan and approval request",
        "dispatch SSH commands to Debian worker",
        "collect and format reports",
    ],
    commands_on_debian=[
        "curl GitHub API (PR details, file contents, tree structures)",
        "git init/commit in /tmp/pr40457-normal (local merge simulation)",
        "python3 py_compile (syntax validation)",
        "vibe_external_authorized_push.py validate/dry-run (wrapper tests)",
        "test_toolchain_smoke.py (130 tests)",
        "vibe_autonomous_merge.py (wrapper merge PR #128)",
        "GitHub Git Data API: create blobs/trees/commit/update ref",
    ],
    git_mutation_node=NODE_DEBIAN,
    token_access_node=NODE_DEBIAN,
    token_access_type="api_auth",
    token_redacted=True,
    pr_operation_node=NODE_DEBIAN,
    api_fallback_used=True,
    api_fallback_node=NODE_DEBIAN,
    failure_node=NODE_DEBIAN,
    failure_description="git push via wrapper failed (PAT 403 on git protocol); fell back to GitHub Git Data API",
    retry_node=NODE_DEBIAN,
    evidence_location="/tmp/pr40457-normal/ (local merge), GitHub API (remote push)",
)

# ── CLI ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, json as _json
    parser = argparse.ArgumentParser(prog="vibe_node_attribution")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument("--format", action="store_true", help="Formatted text output")
    parser.add_argument("--example", action="store_true", help="Output PR #40457 example attribution")
    args = parser.parse_args()

    if args.example:
        attr = PR40457_ATTRIBUTION
    else:
        attr = generate_attribution()

    if args.output_json:
        print(_json.dumps(attr, indent=2))
    elif args.format:
        print(format_attribution(attr))
    else:
        print(format_attribution(attr))