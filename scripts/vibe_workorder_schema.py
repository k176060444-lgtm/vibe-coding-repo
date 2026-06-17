#!/usr/bin/env python3
"""vibe_workorder_schema.py -- Work Order Schema with Capability Fields v1.0.0

Extends the Work Order format with:
  - required_capabilities: list of task types the worker must support
  - required_tools: list of tool names that MUST be present on the worker
  - optional_tools: list of tool names that MAY be present
  - capability_fallback_policy: "block" (fail-closed) or "degrade"

Validates and parses Work Orders from JSON/dict.  Pure validation, no IO.

Usage:
    from vibe_workorder_schema import WorkOrder
    wo = WorkOrder.from_dict(raw_dict)
    wo = WorkOrder.from_json(json_string)
"""

__version__ = "1.0.0"

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional


VALID_FALLBACK_POLICIES = {"block", "degrade"}


@dataclass
class WorkOrder:
    """Structured Work Order with capability requirements."""

    # Core identity
    work_order_id: str
    title: str
    wo_type: str  # code, doc, test, fix, maint
    goal: str

    # Risk / approval
    risk_level: str = "low"  # low, medium, high, critical
    requires_human_approval: bool = False

    # Scope
    allowed_paths: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)

    # Verification
    acceptance_tests: List[str] = field(default_factory=list)
    stop_conditions: List[str] = field(default_factory=list)
    expected_report_fields: List[str] = field(default_factory=list)

    # --- Capability fields (NEW) ---
    required_capabilities: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    optional_tools: List[str] = field(default_factory=list)
    capability_fallback_policy: str = "block"  # "block" | "degrade"

    # Metadata
    version: str = "1.0.0"
    draft_only: bool = True
    execution_requires_explicit_approval: bool = True

    def __post_init__(self):
        if self.capability_fallback_policy not in VALID_FALLBACK_POLICIES:
            raise ValueError(
                "Invalid capability_fallback_policy: %r (expected one of %s)"
                % (self.capability_fallback_policy, VALID_FALLBACK_POLICIES)
            )

    # ---- Construction helpers ----

    @classmethod
    def from_dict(cls, d: dict) -> "WorkOrder":
        """Parse a WorkOrder from a dict.

        Raises ValueError on invalid fallback policy.
        """
        fb = d.get("capability_fallback_policy", "block")
        if fb not in VALID_FALLBACK_POLICIES:
            raise ValueError(
                "Invalid capability_fallback_policy: %r (expected one of %s)"
                % (fb, VALID_FALLBACK_POLICIES)
            )
        return cls(
            work_order_id=d.get("work_order_id", ""),
            title=d.get("title", ""),
            wo_type=d.get("type", d.get("wo_type", "")),
            goal=d.get("goal", ""),
            risk_level=d.get("risk_level", "low"),
            requires_human_approval=d.get("requires_human_approval", False),
            allowed_paths=d.get("allowed_paths", []),
            forbidden_actions=d.get("forbidden_actions", []),
            acceptance_tests=d.get("acceptance_tests", []),
            stop_conditions=d.get("stop_conditions", []),
            expected_report_fields=d.get("expected_report_fields", []),
            required_capabilities=d.get("required_capabilities", []),
            required_tools=d.get("required_tools", []),
            optional_tools=d.get("optional_tools", []),
            capability_fallback_policy=fb,
            version=d.get("version", "1.0.0"),
            draft_only=d.get("draft_only", True),
            execution_requires_explicit_approval=d.get(
                "execution_requires_explicit_approval", True
            ),
        )

    @classmethod
    def from_json(cls, s: str) -> "WorkOrder":
        """Parse a WorkOrder from a JSON string."""
        return cls.from_dict(json.loads(s))

    # ---- Serialisation ----

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    # ---- Validation ----

    def validate(self) -> dict:
        """Validate this Work Order.  Returns {"ok": bool, "errors": [...]}."""
        errors = []
        if not self.work_order_id:
            errors.append("work_order_id is empty")
        if not self.title:
            errors.append("title is empty")
        if not self.goal or len(self.goal.strip()) < 10:
            errors.append("goal is empty or too short (< 10 chars)")
        if self.capability_fallback_policy not in VALID_FALLBACK_POLICIES:
            errors.append(
                "Invalid capability_fallback_policy: %r" % self.capability_fallback_policy
            )
        return {"ok": len(errors) == 0, "errors": errors}


def main():
    import argparse, sys
    parser = argparse.ArgumentParser(description="Work Order Schema v" + __version__)
    parser.add_argument("file", nargs="?", help="JSON file to parse")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.stdin:
        wo = WorkOrder.from_json(sys.stdin.read())
    elif args.file:
        with open(args.file) as f:
            wo = WorkOrder.from_json(f.read())
    else:
        parser.print_help()
        return 1

    if args.validate:
        result = wo.validate()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    else:
        print(wo.to_json())
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
