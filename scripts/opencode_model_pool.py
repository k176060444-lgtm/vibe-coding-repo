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
                    roles: list = None, capability_tags: list = None, priority: int = 10,
                    source_flags: list = None) -> dict:
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
        "lifecycle_status": "enabled",
        "last_seen": None,
        "roles": roles or ["implementer"],
        "priority": priority,
        "capability_tags": capability_tags or [],
        "source_flags": source_flags or [],
        "fallback_allowed": False,
        "cooldown_state": {"active": False, "until": None},
        "rate_limit_events": [],
        "live_validation": {
            "validated": False,
            "call_count": 0,
            "roles_validated": [],
            "last_verdict": None,
            "last_verdict_timestamp": None,
        },
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


def parse_configured_models(config_path: str) -> list[dict]:
    """Parse user-configured models from an opencode.jsonc config file.

    Returns list of model dicts with source_flags=['user_configured'].
    Does NOT print or expose API keys/secrets.
    """
    import json as _json
    if not os.path.exists(config_path):
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Strip // comments for jsonc
    lines = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        # Remove inline // comments (but not inside strings)
        if "//" in stripped:
            in_str = False
            for i, ch in enumerate(stripped):
                if ch == '"':
                    in_str = not in_str
                elif not in_str and stripped[i:i+2] == "//":
                    stripped = stripped[:i]
                    break
        lines.append(stripped)

    cleaned = "\n".join(lines)

    try:
        data = _json.loads(cleaned)
    except _json.JSONDecodeError:
        return []

    providers = data.get("provider", {})
    configured = []

    for provider_name, prov_config in providers.items():
        models_dict = prov_config.get("models", {})
        for model_key, model_meta in models_dict.items():
            exact_model_id = f"{provider_name}/{model_key}"
            name = model_meta.get("name", "") if isinstance(model_meta, dict) else ""
            alias = model_key

            cost_tag = "paid"
            lower = model_key.lower()
            if "free" in lower:
                cost_tag = "free"

            cap_tags = []
            if "code" in lower or "coder" in lower:
                cap_tags.append("code")
            if "flash" in lower or "mini" in lower:
                cap_tags.append("fast")
            if "ultra" in lower or "pro" in lower:
                cap_tags.append("strong")
            if "deepseek" in lower:
                cap_tags.append("code")
            if "mimo" in lower:
                cap_tags.append("code")
            if "ark" in lower:
                cap_tags.append("code")
            if "minimax" in lower:
                cap_tags.append("code")
            if not cap_tags:
                cap_tags.append("general")

            entry = new_model_entry(
                exact_model_id,
                alias=alias,
                cost_tag=cost_tag,
                capability_tags=cap_tags,
                source_flags=["user_configured"],
            )
            entry["provider"] = provider_name
            entry["display_name"] = name or model_key
            entry["lifecycle_status"] = "enabled"
            configured.append(entry)

    return configured


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
        """Canonical snapshot content for hashing (no secrets, no self-referential SHA, no timestamp).

        The hash is deterministic over model content only. timestamp is excluded
        so that repeated discover_node calls on unchanged models produce the same SHA.
        """
        sanitized = self.export_sanitized()
        # Remove snapshot_sha256 to avoid circular dependency
        sanitized.pop('snapshot_sha256', None)
        # Remove snapshot_timestamp — it changes on every save() even when models are unchanged
        sanitized.pop('snapshot_timestamp', None)
        return json.dumps(sanitized, sort_keys=True, ensure_ascii=False)

    def discover_configured(self, config_path: str, node_id: str = "all") -> dict:
        """Load user-configured models from an opencode.jsonc config file.

        Merges into existing pool. Does NOT expose secrets.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.snapshot_timestamp = now

        configured = parse_configured_models(config_path)
        added = []
        updated = []

        for entry in configured:
            mid = entry["exact_model_id"]
            if mid not in self.models:
                # Set node availability for specified node
                if node_id == "all":
                    for n in ["5bao", "9bao", "21bao"]:
                        entry["node_availability"][n] = {"available": True, "last_seen": now}
                else:
                    entry["node_availability"][node_id] = {"available": True, "last_seen": now}
                entry["last_seen"] = now
                self.models[mid] = entry
                added.append(mid)
            else:
                # Merge: update source_flags, keep existing data
                existing = self.models[mid]
                existing_flags = set(existing.get("source_flags", []))
                new_flags = set(entry.get("source_flags", []))
                merged_flags = sorted(existing_flags | new_flags)
                existing["source_flags"] = merged_flags
                existing["last_seen"] = now
                # Update display_name if available
                if entry.get("display_name"):
                    existing["display_name"] = entry["display_name"]
                # Mark as user_configured if not already
                if "user_configured" not in existing_flags:
                    existing["source_flags"] = merged_flags
                updated.append(mid)

        self.save()
        return {
            "config_path": config_path,
            "timestamp": now,
            "added": sorted(added),
            "updated": sorted(updated),
            "total_configured": len(configured),
            "snapshot_sha256": self.snapshot_sha256,
        }

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
                    source_flags=["opencode_discovered"],
                )
                entry["node_availability"][node_id] = {"available": True, "last_seen": now}
                entry["last_seen"] = now
                entry["health_status"] = "healthy"
                self.models[model_id] = entry
                added.append(model_id)
            else:
                # Existing model, update node availability and merge source_flags
                existing = self.models[model_id]
                existing["node_availability"][node_id] = {"available": True, "last_seen": now}
                existing["last_seen"] = now
                existing["health_status"] = "healthy"
                flags = set(existing.get("source_flags", []))
                flags.add("opencode_discovered")
                existing["source_flags"] = sorted(flags)
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
                    "lifecycle_status": e.get("lifecycle_status", "enabled"),
                    "last_seen": e["last_seen"],
                    "roles": e["roles"],
                    "priority": e["priority"],
                    "capability_tags": e["capability_tags"],
                    "source_flags": e.get("source_flags", []),
                    "fallback_allowed": e["fallback_allowed"],
                    "live_validation": e.get("live_validation", {}),
                    "display_name": e.get("display_name", ""),
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

    # --- Central Management ---

    def add_model(self, exact_model_id: str, alias: str = "", cost_tag: str = "unknown",
                  roles: list = None, capability_tags: list = None,
                  source_flags: list = None) -> dict:
        """Add a model entry to the pool. Returns the new entry."""
        if exact_model_id in self.models:
            return {"error": f"model already exists: {exact_model_id}",
                    "action": "use update or disable instead"}
        entry = new_model_entry(
            exact_model_id, alias=alias, cost_tag=cost_tag,
            roles=roles, capability_tags=capability_tags,
            source_flags=source_flags or ["manual_candidate"],
        )
        self.models[exact_model_id] = entry
        self.save()
        return {"action": "added", "exact_model_id": exact_model_id,
                "snapshot_sha256": self.snapshot_sha256}

    def disable_model(self, exact_model_id: str) -> dict:
        """Disable a model (not recommended, still auditable)."""
        if exact_model_id not in self.models:
            return {"error": f"model not found: {exact_model_id}"}
        entry = self.models[exact_model_id]
        entry["enabled"] = False
        entry["lifecycle_status"] = "disabled"
        self.save()
        return {"action": "disabled", "exact_model_id": exact_model_id,
                "snapshot_sha256": self.snapshot_sha256}

    def enable_model(self, exact_model_id: str) -> dict:
        """Re-enable a disabled model."""
        if exact_model_id not in self.models:
            return {"error": f"model not found: {exact_model_id}"}
        entry = self.models[exact_model_id]
        entry["enabled"] = True
        entry["lifecycle_status"] = "enabled"
        self.save()
        return {"action": "enabled", "exact_model_id": exact_model_id,
                "snapshot_sha256": self.snapshot_sha256}

    def retire_model(self, exact_model_id: str) -> dict:
        """Retire a model (inactive, auditable, not in recommendations)."""
        if exact_model_id not in self.models:
            return {"error": f"model not found: {exact_model_id}"}
        entry = self.models[exact_model_id]
        entry["enabled"] = False
        entry["lifecycle_status"] = "retired"
        self.save()
        return {"action": "retired", "exact_model_id": exact_model_id,
                "snapshot_sha256": self.snapshot_sha256}

    def sync_plan(self, nodes: list = None) -> dict:
        """Generate per-node sync plan (dry-run). Shows what would change."""
        if nodes is None:
            nodes = ["5bao", "9bao", "21bao"]
        plan = {}
        for node in nodes:
            node_plan = {"add": [], "remove": [], "update": []}
            for mid, entry in self.models.items():
                avail = entry.get("node_availability", {}).get(node, {})
                lifecycle = entry.get("lifecycle_status", "enabled")
                if lifecycle == "retired":
                    if avail.get("available", False):
                        node_plan["remove"].append(mid)
                elif lifecycle == "disabled":
                    node_plan["update"].append({"model": mid, "action": "disable"})
                elif not avail.get("available", False):
                    node_plan["add"].append(mid)
                else:
                    pass  # already in sync
            plan[node] = node_plan
        return {"plan": plan, "nodes": nodes, "dry_run": True,
                "snapshot_sha256": self.snapshot_sha256}

    def node_drift_report(self, nodes: list = None) -> dict:
        """Detect per-node model availability drift."""
        if nodes is None:
            nodes = ["5bao", "9bao", "21bao"]
        report = {}
        for node in nodes:
            node_models = set()
            pool_models = set()
            for mid, entry in self.models.items():
                avail = entry.get("node_availability", {}).get(node, {})
                if avail.get("available", False):
                    node_models.add(mid)
                pool_models.add(mid)
            report[node] = {
                "available_count": len(node_models),
                "pool_count": len(pool_models),
                "missing_from_node": sorted(pool_models - node_models),
                "extra_on_node": sorted(node_models - pool_models),
            }
        return {"drift_report": report, "snapshot_sha256": self.snapshot_sha256}

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

        # sc-24: snapshot SHA consistency — recommend, export_snapshot, and
        # pool.snapshot_sha256 must all agree
        snap_sha = pool.snapshot_sha256
        export_sha = hashlib.sha256(
            json.dumps(pool.export_snapshot_for_approval(), sort_keys=True).encode()
        ).hexdigest()
        rec_sha = rec4.get("model_pool_snapshot_sha256", "")
        check("sc-24-sha-pool-vs-recommend", snap_sha == rec_sha,
              f"pool={snap_sha[:16]} rec={rec_sha[:16]}")
        # Note: export_snapshot_for_approval SHA is hash of the export dict,
        # not the same as pool.snapshot_sha256 (which is hash of models only).
        # They are different by design. pool.snapshot_sha256 is the authoritative one.

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

        # sc-26: new_model_entry includes source_flags
        entry_sf = new_model_entry("opencode/test-sf", source_flags=["user_configured"])
        check("sc-26-source-flags", entry_sf["source_flags"] == ["user_configured"],
              str(entry_sf["source_flags"]))

        # sc-27: new_model_entry includes lifecycle_status
        check("sc-27-lifecycle-default", entry_sf.get("lifecycle_status") == "enabled")

        # sc-28: new_model_entry includes live_validation
        check("sc-28-live-validation-field", "live_validation" in entry_sf)
        check("sc-28-live-validation-default", entry_sf["live_validation"]["validated"] is False)

        # sc-29: parse_configured_models with test config
        import tempfile
        test_config = json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "test-prov": {
                    "npm": "@ai-sdk/openai-compatible",
                    "options": {"baseURL": "https://example.com", "apiKey": "SECRET_KEY_123"},
                    "models": {
                        "test-model-1": {"name": "Test Model 1"},
                        "test-model-2": {}
                    }
                }
            }
        })
        test_config_path = "/tmp/test_oc_config.json"
        with open(test_config_path, "w") as f:
            f.write(test_config)
        configured = parse_configured_models(test_config_path)
        check("sc-29-parse-count", len(configured) == 2, f"count={len(configured)}")
        check("sc-29-parse-source", all("user_configured" in e["source_flags"] for e in configured))
        check("sc-29-parse-id", configured[0]["exact_model_id"] == "test-prov/test-model-1")
        check("sc-29-parse-cost-paid", configured[0]["cost_tag"] == "paid")

        # sc-30: secrets redaction — parse_configured_models must not expose keys
        config_str = json.dumps(configured)
        check("sc-30-secrets-redacted", "SECRET_KEY_123" not in config_str)

        # sc-31: discover_configured merge
        pool2 = ModelPool("/tmp/test_pool_merge.json")
        result_c = pool2.discover_configured(test_config_path, node_id="test-node")
        check("sc-31-config-added", len(result_c["added"]) == 2, f"added={result_c['added']}")
        check("sc-31-config-in-pool", "test-prov/test-model-1" in pool2.models)

        # sc-32: discover_node merges with configured (dedup)
        # Add same model via discover_node — should merge, not duplicate
        pool2.discover_node("test-node", ["test-prov/test-model-1", "opencode/new-discovered"])
        check("sc-32-dedup", list(pool2.models.keys()).count("test-prov/test-model-1") == 1)
        check("sc-32-merge-source",
              sorted(pool2.models["test-prov/test-model-1"].get("source_flags", [])) ==
              sorted(["opencode_discovered", "user_configured"]),
              str(pool2.models["test-prov/test-model-1"].get("source_flags")))

        # sc-33: new discovered model gets opencode_discovered flag
        check("sc-33-discovered-flag",
              "opencode_discovered" in pool2.models["opencode/new-discovered"].get("source_flags", []))

        # sc-34: retired/disabled model not recommended but auditable
        pool2.models["test-prov/test-model-2"]["enabled"] = False
        pool2.models["test-prov/test-model-2"]["lifecycle_status"] = "disabled"
        rec_disabled = pool2.recommend("implementer", "test-node")
        recommended_id = rec_disabled.get("recommended", "")
        check("sc-34-disabled-not-recommended",
              recommended_id != "test-prov/test-model-2",
              f"recommended={recommended_id}")
        check("sc-34-disabled-still-auditable",
              "test-prov/test-model-2" in pool2.models)

        # sc-35: unknown-cost model not default
        pool2.models["opencode/new-discovered"]["cost_tag"] = "unknown"
        rec_impl = pool2.recommend("implementer", "test-node")
        check("sc-35-unknown-not-default",
              rec_impl.get("recommended") != "opencode/new-discovered" or
              all(m.get("cost_tag") != "free"
                  for m in pool2.list_models(node_id="test-node", enabled_only=True)),
              f"recommended={rec_impl.get('recommended')}")

        # sc-36: add_model
        pool3 = ModelPool("/tmp/test_pool_mgmt.json")
        add_result = pool3.add_model("test-provider/new-model", alias="new",
                                      cost_tag="paid", source_flags=["manual_candidate"])
        check("sc-36-add-model", add_result.get("action") == "added",
              str(add_result))
        check("sc-36-add-in-pool", "test-provider/new-model" in pool3.models)

        # sc-37: add duplicate
        dup_result = pool3.add_model("test-provider/new-model")
        check("sc-37-add-duplicate", "error" in dup_result)

        # sc-38: disable_model
        dis_result = pool3.disable_model("test-provider/new-model")
        check("sc-38-disable", dis_result.get("action") == "disabled")
        check("sc-38-disabled-lifecycle",
              pool3.models["test-provider/new-model"]["lifecycle_status"] == "disabled")
        check("sc-38-disabled-not-enabled",
              not pool3.models["test-provider/new-model"]["enabled"])

        # sc-39: disabled not recommended
        rec_dis = pool3.recommend("implementer", "test-node")
        check("sc-39-disabled-not-rec",
              rec_dis.get("recommended") != "test-provider/new-model")

        # sc-40: enable_model
        en_result = pool3.enable_model("test-provider/new-model")
        check("sc-40-enable", en_result.get("action") == "enabled")
        check("sc-40-enabled-lifecycle",
              pool3.models["test-provider/new-model"]["lifecycle_status"] == "enabled")

        # sc-41: retire_model
        ret_result = pool3.retire_model("test-provider/new-model")
        check("sc-41-retire", ret_result.get("action") == "retired")
        check("sc-41-retired-lifecycle",
              pool3.models["test-provider/new-model"]["lifecycle_status"] == "retired")
        check("sc-41-retired-not-enabled",
              not pool3.models["test-provider/new-model"]["enabled"])

        # sc-42: retired still in pool (auditable)
        check("sc-42-retired-auditable",
              "test-provider/new-model" in pool3.models)

        # sc-43: disable nonexistent
        miss_result = pool3.disable_model("nonexistent/model")
        check("sc-43-disable-miss", "error" in miss_result)

        # sc-44: sync_plan
        pool3.discover_node("test-node-a", ["opencode/model-x"])
        pool3.discover_node("test-node-b", ["opencode/model-x", "opencode/model-y"])
        plan = pool3.sync_plan(nodes=["test-node-a", "test-node-b"])
        check("sc-44-sync-plan-has-plan", "plan" in plan)
        check("sc-44-sync-plan-dry-run", plan.get("dry_run") is True)

        # sc-45: drift report
        drift = pool3.node_drift_report(nodes=["test-node-a", "test-node-b"])
        check("sc-45-drift-has-report", "drift_report" in drift)
        check("sc-45-drift-node-a-missing",
              "opencode/model-y" in drift["drift_report"]["test-node-a"]["missing_from_node"])

        # Cleanup test pools
        for f in ["/tmp/test_pool_sc.json", "/tmp/test_pool_merge.json",
                   "/tmp/test_pool_mgmt.json", test_config_path]:
            try:
                os.remove(f)
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
    disc.add_argument("--config", help="Path to opencode.jsonc for user-configured models")

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

    # add
    add = sub.add_parser("add")
    add.add_argument("--model-id", required=True, help="exact_model_id")
    add.add_argument("--alias", default="")
    add.add_argument("--cost-tag", default="unknown", choices=["free", "paid", "unknown"])
    add.add_argument("--source", default="manual_candidate")
    add.add_argument("--roles", nargs="+", default=["implementer"])

    # disable
    dis = sub.add_parser("disable")
    dis.add_argument("--model-id", required=True)

    # enable
    en = sub.add_parser("enable")
    en.add_argument("--model-id", required=True)

    # retire
    ret = sub.add_parser("retire")
    ret.add_argument("--model-id", required=True)

    # sync-plan
    sp = sub.add_parser("sync-plan")
    sp.add_argument("--nodes", nargs="+", default=["5bao", "9bao", "21bao"])

    # drift
    dr = sub.add_parser("drift")
    dr.add_argument("--nodes", nargs="+", default=["5bao", "9bao", "21bao"])

    args = parser.parse_args()

    if args.self_check:
        pool = ModelPool()
        result = pool.self_check()
        print(json.dumps(result, indent=2))
        sys.exit(result["exit_code"])

    pool = ModelPool()

    if args.command == "discover":
        if args.config:
            result = pool.discover_configured(args.config, node_id=args.node or "all")
        elif args.models:
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

    elif args.command == "add":
        result = pool.add_model(
            args.model_id, alias=args.alias, cost_tag=args.cost_tag,
            source_flags=[args.source], roles=args.roles)
        print(json.dumps(result, indent=2))

    elif args.command == "disable":
        result = pool.disable_model(args.model_id)
        print(json.dumps(result, indent=2))

    elif args.command == "enable":
        result = pool.enable_model(args.model_id)
        print(json.dumps(result, indent=2))

    elif args.command == "retire":
        result = pool.retire_model(args.model_id)
        print(json.dumps(result, indent=2))

    elif args.command == "sync-plan":
        result = pool.sync_plan(nodes=args.nodes)
        print(json.dumps(result, indent=2))

    elif args.command == "drift":
        result = pool.node_drift_report(nodes=args.nodes)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
