#!/usr/bin/env python3
"""Work Order Intake v1 - Convert user requirements into Work Order drafts.

Usage:
    python scripts/vibe_workorder_intake.py <requirement-text> [--json] [--type TYPE] [--priority PRIORITY]
    python scripts/vibe_workorder_intake.py --file <path> [--json] [--type TYPE] [--priority PRIORITY]

Converts natural language requirements into structured Work Order drafts in
Markdown and JSON formats. Generates draft only; does NOT execute tasks.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Generates draft only, never executes.
    - No network calls, no file writes (unless --output specified).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


# ── Risk classification keywords ──
RISK_KEYWORDS = {
    "critical": [
        "security", "credential", "secret", "token", "password", "auth",
        "deploy", "production", "database", "migration", "delete all",
    ],
    "high": [
        "refactor", "breaking change", "api change", "schema",
        "permission", "access control", "merge strategy",
    ],
    "medium": [
        "new script", "new feature", "modify", "update logic",
        "add command", "new endpoint",
    ],
    "low": [
        "documentation", "docs", "readme", "comment", "typo",
        "formatting", "rename", "help text", "example",
    ],
}

# ── Type detection keywords ──
TYPE_KEYWORDS = {
    "code": [
        "script", "function", "class", "module", "api", "cli",
        "command", "implement", "add feature", "new script",
    ],
    "doc": [
        "documentation", "docs", "readme", "guide", "runbook",
        "template", "specification", "spec",
    ],
    "test": [
        "test", "smoke", "e2e", "integration test", "unit test",
        "verification", "validation",
    ],
    "fix": [
        "fix", "bug", "error", "crash", "broken", "issue",
        "regression", "patch",
    ],
    "maint": [
        "cleanup", "archive", "remove unused", "refactor",
        "maintenance", "triage",
    ],
}

# ── Forbidden action patterns ──
FORBIDDEN_PATTERNS = [
    r"(?i)delete\s+(all|everything|repo)",
    r"(?i)force\s+push",
    r"(?i)reset\s+--hard",
    r"(?i)drop\s+table",
    r"(?i)rm\s+-rf\s+/",
    r"(?i)deploy\s+to\s+production",
    r"(?i)change\s+(secret|credential|token|password)",
    r"(?i)modify\s+(ci|workflow|github.actions)",
    r"(?i)grant\s+(admin|root|sudo)",
]

# ── Standard forbidden actions (always included) ──
STANDARD_FORBIDDEN = [
    "Do NOT modify secrets/credentials/CI/workflow/admin/Provider/SSH",
    "Do NOT deploy/tag/release",
    "Do NOT force push or reset",
    "Do NOT delete records or remote branches",
    "Do NOT bypass wrapper gate for merges",
    "Do NOT print/expose PAT/token values",
]

# ── Standard stop conditions ──
STANDARD_STOP_CONDITIONS = [
    "origin/main SHA changes during execution",
    "Changed paths exceed declared scope",
    "py_compile fails on modified Python files",
    "Smoke suite regression (any test fails)",
    "Wrapper gate returns allow_merge=false",
    "audit_tainted lock status changes",
    "Security concern detected in code changes",
]

# ── Standard report fields ──
STANDARD_REPORT_FIELDS = [
    "base_sha",
    "result_sha",
    "post_merge_main_sha",
    "pr_url",
    "pr_number",
    "changed_paths",
    "implementer_model",
    "reviewer_model",
    "job_status",
    "audit_status",
    "smoke_suite_result",
    "wrapper_dry_run",
    "wrapper_merge",
    "operator_snapshot",
    "audit_lock_status",
    "token_leak",
    "bare_gh_pr_merge",
]


def _classify_risk(text):
    """Classify risk level based on requirement text."""
    text_lower = text.lower()
    scores = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for level, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[level] += 1
    # Return highest matching level
    for level in ["critical", "high", "medium", "low"]:
        if scores[level] > 0:
            return level
    return "low"  # Default


def _detect_type(text):
    """Detect Work Order type from requirement text."""
    text_lower = text.lower()
    scores = {}
    for wo_type, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[wo_type] = score
    if scores:
        return max(scores, key=scores.get)
    return "code"  # Default


def _detect_forbidden_actions(text):
    """Detect potentially dangerous actions mentioned in requirements."""
    detected = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text):
            detected.append(re.search(pattern, text).group())
    return detected


def _infer_paths(text):
    """Infer likely allowed paths from requirement text."""
    paths = []
    # Look for explicit file paths
    explicit = re.findall(r'(?:scripts|docs|tests)/[\w._-]+\.py', text)
    paths.extend(explicit)
    # Look for script names
    if re.search(r'(?i)script|\.py|command\s+router', text):
        paths.append("scripts/")
    if re.search(r'(?i)doc|readme|guide|workflow', text):
        paths.append("docs/")
    if re.search(r'(?i)test|smoke|e2e', text):
        paths.append("scripts/test_*.py")
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _generate_acceptance_tests(text, wo_type):
    """Generate acceptance test criteria based on requirement and type."""
    tests = []
    if wo_type in ("code", "fix", "test"):
        tests.append("python -m py_compile passes on all modified Python files")
        tests.append("--help flag works and shows expected options")
    if wo_type in ("code", "fix"):
        tests.append("Smoke suite passes (all existing tests)")
        tests.append("Changed paths strictly within declared scope")
    if wo_type == "doc":
        tests.append("Documentation renders correctly")
        tests.append("All internal links resolve")
        tests.append("Changed paths are docs/ only")
    if wo_type == "test":
        tests.append("New tests pass")
        tests.append("Existing tests still pass")
    # Always include
    tests.append("No secrets/tokens/credentials in changed files")
    tests.append("Standard library only, no new dependencies")
    return tests


def _generate_id(text, wo_type):
    """Generate a Work Order ID."""
    # Extract key words
    words = re.findall(r'[a-z]+', text.lower())
    # Filter common words
    stop = {"a", "an", "the", "to", "for", "of", "in", "on", "at", "is", "it",
            "and", "or", "that", "this", "with", "from", "by", "as", "be", "do"}
    meaningful = [w for w in words if w not in stop and len(w) > 2][:3]
    if not meaningful:
        meaningful = ["new", wo_type]
    name = "-".join(meaningful)
    return "wo-%s-%s-001" % (wo_type, name)


def generate_draft(requirement, wo_type=None, priority=None):
    """Generate a Work Order draft from natural language requirement.

    Args:
        requirement: Natural language requirement text.
        wo_type: Override type detection (code/doc/test/fix/maint).
        priority: Override risk classification (low/medium/high/critical).

    Returns:
        dict with Work Order draft fields.
    """
    # Classify
    risk = priority or _classify_risk(requirement)
    detected_type = wo_type or _detect_type(requirement)
    wo_id = _generate_id(requirement, detected_type)

    # Extract title (first sentence or first 80 chars)
    first_line = requirement.strip().split("\n")[0].strip()
    title = first_line[:80] if len(first_line) <= 80 else first_line[:77] + "..."

    # Infer paths
    allowed_paths = _infer_paths(requirement)
    if not allowed_paths:
        if detected_type == "doc":
            allowed_paths = ["docs/"]
        elif detected_type == "test":
            allowed_paths = ["scripts/test_*.py"]
        else:
            allowed_paths = ["scripts/"]

    # Generate acceptance tests
    acceptance = _generate_acceptance_tests(requirement, detected_type)

    # Detect forbidden actions from text
    detected_forbidden = _detect_forbidden_actions(requirement)
    all_forbidden = STANDARD_FORBIDDEN + [
        "Do NOT: %s" % f for f in detected_forbidden
    ]

    # Determine if human approval needed
    requires_human = risk in ("critical", "high")

    draft = {
        "work_order_id": wo_id,
        "title": title,
        "type": detected_type,
        "goal": requirement.strip(),
        "risk_level": risk,
        "requires_human_approval": requires_human,
        "allowed_paths": allowed_paths,
        "forbidden_actions": all_forbidden,
        "acceptance_tests": acceptance,
        "stop_conditions": STANDARD_STOP_CONDITIONS,
        "expected_report_fields": STANDARD_REPORT_FIELDS,
        "model_policy": {
            "implementer": {
                "primary": "deepseek-plan/deepseek-v4-flash",
                "fallback_models": ["xiaomi-plan/mimo-v2.5"],
            },
            "reviewer": {
                "primary": "xiaomi-plan/mimo-v2.5-pro",
                "fallback_models": [],
            },
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft_only": True,
        "execution_requires_explicit_approval": True,
    }

    return draft


def format_markdown(draft):
    """Format Work Order draft as Markdown."""
    lines = [
        "# Work Order Draft",
        "",
        "**ID**: `%s`" % draft["work_order_id"],
        "**Title**: %s" % draft["title"],
        "**Type**: %s" % draft["type"],
        "**Risk**: %s" % draft["risk_level"],
        "**Human Approval**: %s" % ("REQUIRED" if draft["requires_human_approval"] else "Not required"),
        "",
        "---",
        "",
        "## Goal",
        "",
        draft["goal"],
        "",
        "## Allowed Paths",
        "",
    ]
    for p in draft["allowed_paths"]:
        lines.append("- `%s`" % p)
    lines.extend(["", "## Forbidden Actions", ""])
    for f in draft["forbidden_actions"]:
        lines.append("- %s" % f)
    lines.extend(["", "## Acceptance Tests", ""])
    for i, t in enumerate(draft["acceptance_tests"], 1):
        lines.append("%d. %s" % (i, t))
    lines.extend(["", "## Stop Conditions", ""])
    for s in draft["stop_conditions"]:
        lines.append("- %s" % s)
    lines.extend(["", "## Expected Report Fields", ""])
    for f in draft["expected_report_fields"]:
        lines.append("- `%s`" % f)
    lines.extend([
        "",
        "---",
        "",
        "**⚠️ DRAFT ONLY — This is a proposal, not an executed task.**",
        "**Execution requires explicit human approval.**",
    ])
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_workorder_intake",
        description="Work Order Intake v1 - Convert requirements into Work Order drafts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  vibe_workorder_intake 'Add --summary flag to snapshot'\n"
               "  vibe_workorder_intake 'Update workflow docs' --type doc\n"
               "  vibe_workorder_intake 'Fix advisor crash' --type fix --priority high\n"
               "  vibe_workorder_intake --file requirement.txt --json",
    )
    parser.add_argument(
        "requirement",
        nargs="?",
        default=None,
        help="Natural language requirement text",
    )
    parser.add_argument(
        "--file", "-f",
        help="Read requirement from file",
    )
    parser.add_argument(
        "--type", "-t",
        choices=["code", "doc", "test", "fix", "maint"],
        default=None,
        help="Override auto-detected Work Order type",
    )
    parser.add_argument(
        "--priority", "-p",
        choices=["low", "medium", "high", "critical"],
        default=None,
        help="Override auto-classified risk level",
    )
    parser.add_argument(
        "--json", dest="output_json",
        action="store_true", default=False,
        help="Output in JSON format",
    )
    parser.add_argument(
        "--output", "-o",
        help="Write output to file (default: stdout)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Get requirement text
    requirement = args.requirement
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                requirement = f.read()
        except (OSError, IOError) as e:
            print("ERROR: Cannot read file: %s" % e, file=sys.stderr)
            return 1
    elif requirement is None:
        print("ERROR: Provide requirement text or --file", file=sys.stderr)
        print("Usage: vibe_workorder_intake 'your requirement here'", file=sys.stderr)
        return 1

    if not requirement.strip():
        print("ERROR: Empty requirement", file=sys.stderr)
        return 1

    # Generate draft
    draft = generate_draft(requirement, args.type, args.priority)

    # Format output
    if args.output_json:
        output = json.dumps(draft, indent=2, ensure_ascii=False)
    else:
        output = format_markdown(draft)

    # Write output
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print("Draft written to: %s" % args.output)
        except (OSError, IOError) as e:
            print("ERROR: Cannot write file: %s" % e, file=sys.stderr)
            return 1
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
