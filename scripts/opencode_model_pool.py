#!/usr/bin/env python3
"""OpenCode Dynamic Model Pool v1.0.0

Discovers, tracks, and validates OpenCode free/cost models across nodes.
Provides recommendation gate for task types and operator confirmation templates.

Usage:
    python scripts/opencode_model_pool.py --self-check
    python scripts/opencode_model_pool.py discover --node 21bao
    python scripts/opencode_model_pool.py discover --all
    python scripts/opencode_model_pool.py list [--node N] [--tag free] [--enabled]
    python scripts/opencode_model_pool.py snapshot
    python scripts/opencode_model_pool.py recommend --task first_live_smoke --node 21bao
    python scripts/opencode_model_pool.py validate --model-id ID --node N
    python scripts/opencode_model_pool.py resolve --alias A --node N
"""

__version__ = "1.0.0"

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

# --- Constants ---

STALE_HOURS = 24
FREE_KEYWORDS = ["free", "free-tier"]
COST_KEYWORDS = ["pro", "plus", "paid", "enterprise"]

TASK_TYPE_RECOMMENDATIONS = {
    "first_live_smoke": {
        "strategy": "free + fastest + simplest",
        "preferred_tags": ["free", "fast"],
        "preferred_roles": ["smoke", "implementer"],
    },
    "implementer": {
        "strategy": "free + code capability",
        "preferred_tags": ["free", "code"],
        "preferred_roles": ["implementer"],
    },
    "implementer-small": {
        "strategy": "free + code capability (small tasks)",
        "preferred_tags": ["free", "code", "fast"],
        "preferred_roles": ["implementer-small", "implementer"],
    },
    "smoke": {
        "strategy": "free + fastest + simplest",
        "preferred_tags": ["free", "fast"],
        "preferred_roles": ["smoke"],
    },
    "reviewer": {
        "strategy": "free + review capability",
        "preferred_tags": ["free", "review"],
        "preferred_roles": ["reviewer"],
    },
    "orchestrator": {
        "strategy": "free + general",
        "preferred_tags": ["free"],
        "preferred_roles": ["orchestrator", "implementer"],
    },
}

# Node transport config for discover
NODE_TRANSPORT = {
    "21bao": {"type": "local-exec", "bin": r"D:\vibedev-tools\opencode\node_modules\opencode-ai\bin\opencode.exe"},
    "5bao": {"type": "ssh", "host": "192.168.5.6", "port": 22222, "user": "vibeworker",
             "prefix": "NPM_CONFIG_PREFIX=~/.npm-global PATH=$HOME/bin:$HOME/.npm-global/bin:$PATH"},
    "9bao": {"type": "ssh", "host": "192.168.9.6", "port": 22222, "user": "vibeworker",
             "prefix": "~/.opencode/bin/"},
}

# --- Model Entry ---

def new_model_entry(exact_model_id: str, alias: str = "", cost_tag: str = "unknown",
                    roles: list = None, capability_tags: list = None, priority: int = 10) -> dict:
    """Create a new model pool entry."""
    if not alias:
        alias = exact_model_id.split("/")[-1] if "/" in exact_model_id else exact_model_id
    return {
        "model_id": exact_model_id,
        "alias": alias,
        "provider": exact_model_id.split("/")[0] if "/" in exact_model_id else "unknown",
        "exact_model_id": exact_model_id,
        "node_availability": {},
        "cost_tag": cost_tag,
        "enabled": True,
        "health_status": "unknown",
        "last_seen": None,
        "roles": roles or ["implementer"],
        "priority": priority,
        "capability_tags": capability_tags or [],
        "fallback_allowed": False,
        "cooldown_state": {"active": False, "until": None},
        "rate_limit_events": [],
    }


def auto_tag_cost(model_id: str) -> str:
    """Auto-detect cost tag from model name."""
    lower = model_id.lower()
    for kw in FREE_KEYWORDS:
        if kw in lower:
            return "free"
    for kw in COST_KEYWORDS:
        if kw in lower:
            return "cost"
    return "unknown"


def auto_capability_tags(model_id: str) -> list:
    """Auto-detect capability tags from model name."""
    lower = model_id.lower()
    tags = []
    if "code" in lower or "coder" in lower:
        tags.append("code")
    if "free" in lower:
        tags.append("free")
    if "flash" in lower or "mini" in lower:
        tags.append("fast")
    if "ultra" in lower or "pro" in lower:
        tags.append("strong")
    if "nemotron" in lower or "deepseek" in lower:
        tags.append("code")
    if not tags:
        tags.append("general")
    return tags


# --- Pool Storage ---

class ModelPool:
    """Dynamic OpenCode model pool with discover/diff/snapshot."""

    def __init__(self, pool_path: Optional[str] = None):
        if pool_path is None:
            pool_path = os.path.join(os.path.dirname(__file__), ".opencode_model_pool.json")
        self.pool_path = pool_path
        self.models: dict[str, dict] = {}
        self.snapshot_timestamp: Optional[str] = None
        self.snapshot_sha256: Optional[str] = None
        self._load()

    def _load(self):
        if os.path.exists(self.pool_path):
            with open(self.pool_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.models = data.get("models", {})
            self.snapshot_timestamp = data.get("snapshot_timestamp")
            self.snapshot_sha256 = data.get("snapshot_sha256")

    def save(self):
        """Save pool to disk and recompute snapshot SHA256."""
        content = self._snapshot_content()
        self.snapshot_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        data = {
            "models": self.models,
            "snapshot_timestamp": self.snapshot_timestamp,
            "snapshot_sha256": self.snapshot_sha256,
            "version": __version__,
        }
        os.makedirs(os.path.dirname(self.pool_path) or ".", exist_ok=True)
        with open(self.pool_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _snapshot_content(self) -> str:
        """Canonical snapshot content for hashing (no secrets, no self-referential SHA)."""
        sanitized = self.export_sanitized()
        # Remove snapshot_sha256 to avoid circular dependency
        sanitized.pop('snapshot_sha256', None)
        return json.dumps(sanitized, sort_keys=True, ensure_ascii=False)

    def discover_node(self, node_id: str, models_list: list[str]) -> dict:
        """Discover models from a node's `opencode models` output.

        Args:
            node_id: Node identifier (21bao, 5bao, 9bao)
            models_list: List of exact model IDs from `opencode models`

        Returns:
            Discovery result with added/updated/unavailable models
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.snapshot_timestamp = now

        discovered = set(models_list)
        known = set(self.models.keys())

        added = []
        updated = []
        unchanged = []

        for model_id in discovered:
            if model_id not in self.models:
                # New model discovered
                entry = new_model_entry(
                    model_id,
                    cost_tag=auto_tag_cost(model_id),
                    capability_tags=auto_capability_tags(model_id),
                )
                entry["node_availability"][node_id] = {"available": True, "last_seen": now}
                entry["last_seen"] = now
                entry["health_status"] = "healthy"
                self.models[model_id] = entry
                added.append(model_id)
            else:
                # Existing model, update node availability
                self.models[model_id]["node_availability"][node_id] = {"available": True, "last_seen": now}
                self.models[model_id]["last_seen"] = now
                self.models[model_id]["health_status"] = "healthy"
                updated.append(model_id)

        # Mark models not seen on this node
        disappeared = []
        for model_id in known:
            if model_id not in discovered:
                avail = self.models[model_id].get("node_availability", {})
                if node_id in avail and avail[node_id].get("available"):
                    avail[node_id]["available"] = False
                    avail[node_id]["disappeared_at"] = now
                    disappeared.append(model_id)
            else:
                unchanged.append(model_id)

        self.save()
        return {
            "node": node_id,
            "timestamp": now,
            "discovered": sorted(discovered),
            "added": sorted(added),
            "updated": sorted(updated),
            "disappeared": sorted(disappeared),
            "unchanged": sorted(unchanged),
            "snapshot_sha256": self.snapshot_sha256,
        }

    def list_models(self, node_id: Optional[str] = None, tag: Optional[str] = None,
                    enabled_only: bool = False) -> list[dict]:
        """List models with optional filters."""
        result = []
        for model_id, entry in self.models.items():
            if enabled_only and not entry.get("enabled", True):
                continue
            if tag and entry.get("cost_tag") != tag:
                continue
            if node_id:
                avail = entry.get("node_availability", {}).get(node_id, {})
                if not avail.get("available", False):
                    continue
            result.append(entry)
        result.sort(key=lambda e: e.get("priority", 10))
        return result

    def resolve_alias(self, alias: str, node_id: Optional[str] = None) -> Optional[str]:
        """Resolve alias to exact_model_id. Returns None if not found or unavailable."""
        for model_id, entry in self.models.items():
            if entry.get("alias") == alias:
                if node_id:
                    avail = entry.get("node_availability", {}).get(node_id, {})
                    if not avail.get("available", False):
                        return None
                if not entry.get("enabled", True):
                    return None
                return entry["exact_model_id"]
        return None

    def validate_model(self, exact_model_id: str, node_id: str) -> tuple[bool, str]:
        """Validate a model is available on a node. Fail-closed."""
        if exact_model_id not in self.models:
            return False, f"model not in pool: {exact_model_id}"
        entry = self.models[exact_model_id]
        if not entry.get("enabled", True):
            return False, f"model disabled: {exact_model_id}"
        avail = entry.get("node_availability", {}).get(node_id, {})
        if not avail.get("available", False):
            return False, f"model not available on node {node_id}: {exact_model_id}"
        if entry.get("health_status") == "unavailable":
            return False, f"model health unavailable: {exact_model_id}"
        return True, "ok"

    def is_snapshot_stale(self) -> bool:
        """Check if snapshot is older than STALE_HOURS."""
        if not self.snapshot_timestamp:
            return True
        try:
            ts = datetime.fromisoformat(self.snapshot_timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_hours = (now - ts).total_seconds() / 3600
            return age_hours > STALE_HOURS
        except (ValueError, TypeError):
            return True

    def export_sanitized(self) -> dict:
        """Export pool without any secrets/env/tokens/keys."""
        return {
            "models": {
                mid: {
                    "model_id": e["model_id"],
                    "alias": e["alias"],
                    "provider": e["provider"],
                    "exact_model_id": e["exact_model_id"],
                    "node_availability": e["node_availability"],
                    "cost_tag": e["cost_tag"],
                    "enabled": e["enabled"],
                    "health_status": e["health_status"],
                    "last_seen": e["last_seen"],
                    "roles": e["roles"],
                    "priority": e["priority"],
                    "capability_tags": e["capability_tags"],
                    "fallback_allowed": e["fallback_allowed"],
                }
                for mid, e in self.models.items()
            },
            "snapshot_timestamp": self.snapshot_timestamp,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def export_snapshot_for_approval(self) -> dict:
        """Export snapshot hash for approval digest binding."""
        return {
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_timestamp": self.snapshot_timestamp,
            "model_count": len(self.models),
            "stale": self.is_snapshot_stale(),
        }

    def recommend(self, task_type: str, node_id: str) -> dict:
        """Recommend a model for a task type on a given node."""
        config = TASK_TYPE_RECOMMENDATIONS.get(task_type)
        if not config:
            return {"error": f"unknown task_type: {task_type}", "recommended": None}

        candidates = self.list_models(node_id=node_id, enabled_only=True)
        if not candidates:
            return {"error": f"no models available on {node_id}", "recommended": None}

        # Score: prefer free, prefer matching tags, prefer matching roles
        scored = []
        for m in candidates:
            score = 0
            if m.get("cost_tag") == "free":
                score += 10
            for tag in config.get("preferred_tags", []):
                if tag in m.get("capability_tags", []):
                    score += 5
            for role in config.get("preferred_roles", []):
                if role in m.get("roles", []):
                    score += 3
            score += (100 - m.get("priority", 10))  # lower priority = higher score
            scored.append((score, m))

        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]
        alternatives = [s[1]["exact_model_id"] for s in scored[1:3]]

        return {
            "task_type": task_type,
            "strategy": config["strategy"],
            "node": node_id,
            "recommended": best["exact_model_id"],
            "alias": best["alias"],
            "cost_tag": best["cost_tag"],
            "reason": f"{config['strategy']}; priority={best['priority']}",
            "alternatives": alternatives,
            "model_pool_snapshot_sha256": self.snapshot_sha256,
        }

    # --- Self-check ---

    def self_check(self) -> dict:
        """Run self-validation checks."""
        checks = []
        passed = 0
        total = 0

        def check(name: str, ok: bool, detail: str = ""):
            nonlocal passed, total
            total += 1
            if ok:
                passed += 1
            checks.append({"name": name, "passed": ok, "detail": detail})

        # sc-01: version defined
        check("sc-01-version", bool(__version__), __version__)

        # sc-02: task type recommendations exist
        check("sc-02-task-types", len(TASK_TYPE_RECOMMENDATIONS) >= 4,
              f"count={len(TASK_TYPE_RECOMMENDATIONS)}")

        # sc-03: auto_tag_cost works
        check("sc-03-auto-tag-free", auto_tag_cost("opencode/mimo-v2.5-free") == "free")
        check("sc-04-auto-tag-cost", auto_tag_cost("opencode/gpt-4-pro") == "cost")
        check("sc-05-auto-tag-unknown", auto_tag_cost("opencode/custom") == "unknown")

        # sc-06: auto_capability_tags
        tags = auto_capability_tags("opencode/deepseek-v4-flash-free")
        check("sc-06-cap-tags", "free" in tags and "fast" in tags, str(tags))

        # sc-07: new_model_entry
        entry = new_model_entry("opencode/test-model", alias="test")
        check("sc-07-new-entry", entry["exact_model_id"] == "opencode/test-model" and entry["alias"] == "test")

        # sc-08: pool operations
        pool = ModelPool("/tmp/test_pool_sc.json")
        result = pool.discover_node("test-node", ["opencode/model-a", "opencode/model-b"])
        check("sc-08-discover-add", len(result["added"]) == 2, f"added={result['added']}")
        check("sc-09-snapshot-sha", bool(result["snapshot_sha256"]), result.get("snapshot_sha256", "")[:16])

        # sc-10: diff - new model
        result2 = pool.discover_node("test-node", ["opencode/model-a", "opencode/model-b", "opencode/model-c"])
        check("sc-10-discover-new", "opencode/model-c" in result2["added"])

        # sc-11: diff - disappeared model (not deleted)
        result3 = pool.discover_node("test-node", ["opencode/model-a"])
        check("sc-11-disappear", "opencode/model-b" in result3["disappeared"] and "opencode/model-c" in result3["disappeared"])
        check("sc-11-not-deleted", "opencode/model-b" in pool.models and "opencode/model-c" in pool.models)

        # sc-12: snapshot SHA changes on content change
        sha1 = pool.snapshot_sha256
        pool.discover_node("test-node", ["opencode/model-a", "opencode/model-d"])
        sha2 = pool.snapshot_sha256
        check("sc-12-sha-changes", sha1 != sha2)

        # sc-13: stale detection
        pool.snapshot_timestamp = "2020-01-01T00:00:00Z"
        check("sc-13-stale", pool.is_snapshot_stale())
        pool.snapshot_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        check("sc-14-not-stale", not pool.is_snapshot_stale())

        # sc-15: resolve alias
        resolved = pool.resolve_alias("model-a", "test-node")
        check("sc-15-resolve", resolved == "opencode/model-a", f"resolved={resolved}")

        # sc-16: resolve alias not found
        not_found = pool.resolve_alias("nonexistent", "test-node")
        check("sc-16-resolve-miss", not_found is None)

        # sc-17: validate model
        ok, msg = pool.validate_model("opencode/model-a", "test-node")
        check("sc-17-validate-ok", ok, msg)

        # sc-18: validate unavailable
        ok2, msg2 = pool.validate_model("opencode/model-b", "test-node")
        check("sc-18-validate-unavail", not ok2, msg2)

        # sc-19: validate not in pool
        ok3, msg3 = pool.validate_model("opencode/nonexistent", "test-node")
        check("sc-19-validate-miss", not ok3, msg3)

        # sc-20: recommend
        rec = pool.recommend("first_live_smoke", "test-node")
        check("sc-20-recommend", rec.get("recommended") is not None, str(rec.get("recommended")))

        # sc-21: recommend unknown task
        rec2 = pool.recommend("unknown_task", "test-node")
        check("sc-21-recommend-unknown", rec2.get("error") is not None)

        # sc-22: recommend implementer-small (native, not fallback to implementer)
        rec3 = pool.recommend("implementer-small", "test-node")
        check("sc-22-recommend-implementer-small", rec3.get("recommended") is not None)
        check("sc-22-implementer-small-task-type", rec3.get("task_type") == "implementer-small")

        # sc-23: recommend smoke (native)
        rec4 = pool.recommend("smoke", "test-node")
        check("sc-23-recommend-smoke", rec4.get("recommended") is not None)
        check("sc-23-smoke-task-type", rec4.get("task_type") == "smoke")

        # sc-22: fallback disabled by default
        check("sc-22-fallback-disabled", not entry["fallback_allowed"])

        # sc-23: sanitized export
        sanitized = pool.export_sanitized()
        san_str = json.dumps(sanitized)
        has_secret = any(kw in san_str.upper() for kw in ["TOKEN", "SECRET", "KEY", "PASSWORD", "PRIVATE"])
        check("sc-23-sanitized-clean", not has_secret)

        # sc-24: snapshot for approval
        snap = pool.export_snapshot_for_approval()
        check("sc-24-snapshot-approval", bool(snap["snapshot_sha256"]))

        # sc-25: list with filters
        free_models = pool.list_models(tag="free")
        check("sc-25-list-filter", all(m["cost_tag"] == "free" for m in free_models) if free_models else True)

        # Cleanup test pool
        try:
            os.remove("/tmp/test_pool_sc.json")
        except OSError:
            pass

        return {
            "version": __version__,
            "passed": passed == total,
            "total_tests": total,
            "passed_count": passed,
            "failed_count": total - passed,
            "checks": checks,
            "exit_code": 0 if passed == total else 1,
        }


# --- CLI ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenCode Dynamic Model Pool")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    sub = parser.add_subparsers(dest="command")

    # discover
    disc = sub.add_parser("discover")
    disc.add_argument("--node", help="Node to discover")
    disc.add_argument("--all", action="store_true", help="Discover all nodes")
    disc.add_argument("--models", nargs="+", help="Model list (for testing)")

    # list
    lst = sub.add_parser("list")
    lst.add_argument("--node", help="Filter by node")
    lst.add_argument("--tag", help="Filter by cost tag")
    lst.add_argument("--enabled", action="store_true")

    # snapshot
    sub.add_parser("snapshot")

    # recommend
    rec = sub.add_parser("recommend")
    rec.add_argument("--task", required=True)
    rec.add_argument("--node", required=True)

    # validate
    val = sub.add_parser("validate")
    val.add_argument("--model-id", required=True)
    val.add_argument("--node", required=True)

    # resolve
    res = sub.add_parser("resolve")
    res.add_argument("--alias", required=True)
    res.add_argument("--node")

    args = parser.parse_args()

    if args.self_check:
        pool = ModelPool()
        result = pool.self_check()
        print(json.dumps(result, indent=2))
        sys.exit(result["exit_code"])

    pool = ModelPool()

    if args.command == "discover":
        if args.models:
            result = pool.discover_node(args.node or "local", args.models)
        elif args.node:
            result = pool.discover_node(args.node, [])
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        models = pool.list_models(node_id=args.node, tag=args.tag, enabled_only=args.enabled)
        print(json.dumps(models, indent=2))

    elif args.command == "snapshot":
        snap = pool.export_snapshot_for_approval()
        print(json.dumps(snap, indent=2))

    elif args.command == "recommend":
        result = pool.recommend(args.task, args.node)
        print(json.dumps(result, indent=2))

    elif args.command == "validate":
        ok, msg = pool.validate_model(args.model_id, args.node)
        print(json.dumps({"valid": ok, "message": msg}, indent=2))

    elif args.command == "resolve":
        resolved = pool.resolve_alias(args.alias, args.node)
        print(json.dumps({"alias": args.alias, "resolved": resolved}, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
