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

# --- V1.21.7: Fuzzy Alias Resolution ---

# Canonical alias → exact_model_id mappings (exact match, no ambiguity)
EXACT_ALIAS_MAP = {
    "deepseek pro": "deepseek-plan/deepseek-v4-pro",
    "deepseek flash": "deepseek-plan/deepseek-v4-flash",
    "ds-v4-pro": "deepseek-plan/deepseek-v4-pro",
    "ds-v4-flash": "deepseek-plan/deepseek-v4-flash",
    "mimo pro": "xiaomi-plan/mimo-v2.5-pro",
    "mimo-v2.5-pro": "xiaomi-plan/mimo-v2.5-pro",
    "mimo-v2.5": "xiaomi-plan/mimo-v2.5",
    "doubao": "volcengine-plan/ark-code-latest",
    "volcengine": "volcengine-plan/ark-code-latest",
    "ark-code": "volcengine-plan/ark-code-latest",
    "ark-code-latest": "volcengine-plan/ark-code-latest",
    "minimax": "minimax-plan/MiniMax-M3",
    "m3": "minimax-plan/MiniMax-M3",
    "minimax-m3": "minimax-plan/MiniMax-M3",
    "MiniMax-M3": "minimax-plan/MiniMax-M3",
    "deepseek-v4-flash-free": "opencode/deepseek-v4-flash-free",
    "mimo-v2.5-free": "opencode/mimo-v2.5-free",
    "nemotron-3-ultra-free": "opencode/nemotron-3-ultra-free",
    "north-mini-code-free": "opencode/north-mini-code-free",
    "big-pickle": "opencode/big-pickle",
}

# Ambiguous aliases → list of candidate exact_model_ids
AMBIGUOUS_ALIAS_MAP = {
    "mimo": [
        "xiaomi-plan/mimo-v2.5",
        "xiaomi-plan/mimo-v2.5-pro",
        "opencode/mimo-v2.5-free",
    ],
    "deepseek": [
        "deepseek-plan/deepseek-v4-flash",
        "deepseek-plan/deepseek-v4-pro",
        "opencode/deepseek-v4-flash-free",
    ],
    "deepseek v4": [
        "deepseek-plan/deepseek-v4-flash",
        "deepseek-plan/deepseek-v4-pro",
        "opencode/deepseek-v4-flash-free",
    ],
    "ds": [
        "deepseek-plan/deepseek-v4-flash",
        "deepseek-plan/deepseek-v4-pro",
        "opencode/deepseek-v4-flash-free",
    ],
}

# Known quarantine reasons (from model-routing-fixture.json)
KNOWN_QUARANTINE = {
    "volcengine-plan/ark-code-latest": "key_format_incorrect",
}

# --- V1.21.7: Static Known Models Seed ---
# Used when no .opencode_model_pool.json snapshot exists.
# Source: opencode.jsonc (user_configured) + model-routing-fixture.json (opencode_discovered)

KNOWN_MODELS_SEED = [
    # --- user_configured (from opencode.jsonc) ---
    {
        "exact_model_id": "deepseek-plan/deepseek-v4-flash",
        "alias": "deepseek-v4-flash",
        "provider": "deepseek-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code", "fast"],
        "roles": ["implementer", "reviewer", "explorer"],
        "priority": 5,
        "display_name": "DeepSeek V4 Flash",
        "recommended_roles": ["Explorer", "Tester"],
    },
    {
        "exact_model_id": "deepseek-plan/deepseek-v4-pro",
        "alias": "deepseek-v4-pro",
        "provider": "deepseek-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code", "strong"],
        "roles": ["implementer", "reviewer"],
        "priority": 3,
        "display_name": "DeepSeek V4 Pro",
        "recommended_roles": ["Reviewer", "Implementer"],
    },
    {
        "exact_model_id": "volcengine-plan/ark-code-latest",
        "alias": "ark-code-latest",
        "provider": "volcengine-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code"],
        "roles": ["implementer", "explorer"],
        "priority": 8,
        "display_name": "Ark Code Latest",
        "recommended_roles": ["Explorer"],
    },
    {
        "exact_model_id": "xiaomi-plan/mimo-v2.5",
        "alias": "mimo-v2.5",
        "provider": "xiaomi-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code"],
        "roles": ["implementer", "explorer"],
        "priority": 6,
        "display_name": "MiMo V2.5",
        "recommended_roles": ["Explorer", "Tester"],
    },
    {
        "exact_model_id": "xiaomi-plan/mimo-v2.5-pro",
        "alias": "mimo-v2.5-pro",
        "provider": "xiaomi-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code", "strong"],
        "roles": ["implementer", "reviewer"],
        "priority": 4,
        "display_name": "MiMo V2.5 Pro",
        "recommended_roles": ["Implementer", "Reviewer"],
    },
    {
        "exact_model_id": "minimax-plan/MiniMax-M3",
        "alias": "MiniMax-M3",
        "provider": "minimax-plan",
        "cost_tag": "paid",
        "source_flags": ["user_configured"],
        "capability_tags": ["code"],
        "roles": ["implementer", "reviewer"],
        "priority": 5,
        "display_name": "MiniMax M3",
        "recommended_roles": ["Implementer"],
    },
    # --- opencode_discovered (from model-routing-fixture.json) ---
    {
        "exact_model_id": "opencode/deepseek-v4-flash-free",
        "alias": "deepseek-v4-flash-free",
        "provider": "opencode",
        "cost_tag": "free",
        "source_flags": ["opencode_discovered"],
        "capability_tags": ["code", "fast", "free"],
        "roles": ["smoke", "implementer", "implementer-small"],
        "priority": 2,
        "display_name": "DeepSeek V4 Flash Free",
        "recommended_roles": ["smoke", "implementer-small"],
    },
    {
        "exact_model_id": "opencode/mimo-v2.5-free",
        "alias": "mimo-v2.5-free",
        "provider": "opencode",
        "cost_tag": "free",
        "source_flags": ["opencode_discovered"],
        "capability_tags": ["code", "free"],
        "roles": ["smoke", "implementer", "implementer-small"],
        "priority": 3,
        "display_name": "MiMo V2.5 Free",
        "recommended_roles": ["smoke", "implementer-small"],
    },
    {
        "exact_model_id": "opencode/nemotron-3-ultra-free",
        "alias": "nemotron-3-ultra-free",
        "provider": "opencode",
        "cost_tag": "free",
        "source_flags": ["opencode_discovered"],
        "capability_tags": ["code", "strong", "free"],
        "roles": ["implementer", "reviewer"],
        "priority": 4,
        "display_name": "Nemotron 3 Ultra Free",
        "recommended_roles": ["reviewer", "implementer"],
    },
    {
        "exact_model_id": "opencode/north-mini-code-free",
        "alias": "north-mini-code-free",
        "provider": "opencode",
        "cost_tag": "free",
        "source_flags": ["opencode_discovered"],
        "capability_tags": ["code", "fast", "free"],
        "roles": ["implementer-small", "smoke"],
        "priority": 5,
        "display_name": "North Mini Code Free",
        "recommended_roles": ["implementer-small", "smoke"],
    },
    {
        "exact_model_id": "opencode/big-pickle",
        "alias": "big-pickle",
        "provider": "opencode",
        "cost_tag": "free",
        "source_flags": ["opencode_discovered"],
        "capability_tags": ["general", "free"],
        "roles": ["orchestrator", "implementer"],
        "priority": 6,
        "display_name": "Big Pickle",
        "recommended_roles": ["orchestrator", "general"],
    },
]

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
                    source_flags: list = None,
                    endpoint: str = "", protocol: str = "openai-compatible",
                    secret_ref: str = "", credential_status: str = "missing",
                    quarantine_status: str = "none") -> dict:
    """Create a new model pool entry."""
    if not alias:
        alias = exact_model_id.split("/")[-1] if "/" in exact_model_id else exact_model_id
    # Validate endpoint doesn't contain secrets
    if endpoint:
        _validate_endpoint_no_secrets(endpoint)
    # Validate secret_ref is a placeholder, not a real key
    if secret_ref:
        _validate_secret_ref_placeholder(secret_ref)
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
        "endpoint": endpoint,
        "protocol": protocol,
        "secret_ref": secret_ref,
        "credential_status": credential_status,
        "quarantine_status": quarantine_status,
    }


# --- Security Validation ---

DANGEROUS_FIELD_NAMES = {
    "key", "api_key", "token", "secret_value", "password", "access_token",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "VOLCENGINE_API_KEY", "XIAOMI_API_KEY",
    "MINIMAX_API_KEY", "secret_key", "private_key", "auth_token",
}

DANGEROUS_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{10,}",
    r"AKIA[A-Z0-9]{16}",
    r"Bearer [a-zA-Z0-9]{10,}",
    r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
]

ENDPOINT_SECRET_PATTERNS = [
    r"[?&](api_key|token|secret|password|key|access_token)=",
    r"://[^:]+:[^@]+@",  # userinfo with password
]


def _validate_endpoint_no_secrets(endpoint: str) -> None:
    """Validate endpoint URL doesn't contain secrets. Raises ValueError if found."""
    import re as _re
    for pattern in ENDPOINT_SECRET_PATTERNS:
        if _re.search(pattern, endpoint, _re.IGNORECASE):
            raise ValueError(f"endpoint contains suspected secret: {endpoint[:50]}...")


def _validate_secret_ref_placeholder(secret_ref: str) -> None:
    """Validate secret_ref is a placeholder, not a real key. Raises ValueError if found."""
    import re as _re
    for pattern in DANGEROUS_KEY_PATTERNS:
        if _re.search(pattern, secret_ref, _re.IGNORECASE):
            raise ValueError(f"secret_ref contains suspected real key")
    # Must start with secret: or be empty
    if secret_ref and not secret_ref.startswith("secret:"):
        raise ValueError(f"secret_ref must start with 'secret:' or be empty")


def _validate_no_dangerous_fields(kwargs: dict) -> None:
    """Validate no dangerous field names are passed. Raises ValueError if found."""
    for key in kwargs:
        if key.lower() in {f.lower() for f in DANGEROUS_FIELD_NAMES}:
            raise ValueError(f"dangerous field name rejected: {key}")


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

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ModelPool":
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        pool = cls()
        for model in yaml_data.get("models", []):
            model_id = model["id"]
            entry = {
                "exact_model_id": model_id,
                "model_id": model.get("model"),
                "alias": model.get("alias", []),
                "provider": model.get("provider"),
                "enabled": model.get("enabled", True),
                "status": model.get("status", "confirmed"),
                "allowed_nodes": model.get("allowed_nodes", []),
                "smoke_required": model.get("smoke_required", False),
                "smoke_results": model.get("smoke_results", {}),
                "priority": model.get("priority", 100),
                "node_availability": {n: {"available": True} for n in model.get("allowed_nodes", [])},
                "health_status": "healthy"
            }
            pool.models[model_id] = entry
        return pool

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
                    enabled_only: bool = False, enforce_guards: bool = False) -> list[dict]:
        """List models with optional filters."""
        result = []
        for model_id, entry in self.models.items():
            if enabled_only and not entry.get("enabled", True):
                continue
            if tag and entry.get("cost_tag") != tag:
                continue

            # Model selection guards
            if enforce_guards:
                # 1. Exclude temporary_unavailable models
                if entry.get("status") == "temporary_unavailable":
                    continue
                # 2. Exclude xiaomi/mimo models
                if entry.get("provider") == "xiaomi" or "mimo" in model_id.lower():
                    continue
                if node_id:
                    # 3. Check node_id is in allowed_nodes
                    allowed_nodes = entry.get("allowed_nodes", [])
                    if allowed_nodes and node_id not in allowed_nodes:
                        continue
                    # 4. Check smoke status if required
                    if entry.get("smoke_required", False):
                        smoke_results = entry.get("smoke_results", {})
                        node_smoke = smoke_results.get(node_id, {})
                        if node_smoke.get("status") != "confirmed":
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

    def validate_model(self, exact_model_id: str, node_id: str, enforce_guards: bool = False) -> tuple[bool, str]:
        """Validate a model is available on a node. Fail-closed."""
        if exact_model_id not in self.models:
            return False, f"model not in pool: {exact_model_id}"
        entry = self.models[exact_model_id]
        if not entry.get("enabled", True):
            return False, f"model disabled: {exact_model_id}"

        # Model selection guards
        if enforce_guards:
            # 1. Exclude temporary_unavailable models
            if entry.get("status") == "temporary_unavailable":
                return False, f"model marked temporary_unavailable: {exact_model_id}"
            # 2. Exclude xiaomi/mimo models
            if entry.get("provider") == "xiaomi" or "mimo" in exact_model_id.lower():
                return False, f"mimo/xiaomi models are blocked: {exact_model_id}"
            # 3. Check node_id is in allowed_nodes
            allowed_nodes = entry.get("allowed_nodes", [])
            if allowed_nodes and node_id not in allowed_nodes:
                return False, f"model not allowed on node {node_id}: {exact_model_id}"
            # 4. Check smoke status if required
            if entry.get("smoke_required", False):
                smoke_results = entry.get("smoke_results", {})
                node_smoke = smoke_results.get(node_id, {})
                if node_smoke.get("status") != "confirmed":
                    return False, f"model smoke not confirmed on node {node_id}: {exact_model_id}"

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
                    "endpoint": e.get("endpoint", ""),
                    "protocol": e.get("protocol", "openai-compatible"),
                    "secret_ref": e.get("secret_ref", ""),
                    "credential_status": e.get("credential_status", "missing"),
                    "quarantine_status": e.get("quarantine_status", "none"),
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
                  source_flags: list = None,
                  endpoint: str = "", protocol: str = "openai-compatible",
                  secret_ref: str = "", credential_status: str = "missing",
                  **kwargs) -> dict:
        """Add a model entry to the pool. Returns the new entry.

        Security: rejects dangerous field names and real key patterns.
        """
        # Reject dangerous field names
        _validate_no_dangerous_fields(kwargs)
        if exact_model_id in self.models:
            return {"error": f"model already exists: {exact_model_id}",
                    "action": "use update or disable instead"}
        entry = new_model_entry(
            exact_model_id, alias=alias, cost_tag=cost_tag,
            roles=roles, capability_tags=capability_tags,
            source_flags=source_flags or ["manual_candidate"],
            endpoint=endpoint, protocol=protocol,
            secret_ref=secret_ref, credential_status=credential_status,
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

    def delete_model(self, exact_model_id: str, force: bool = False,
                     active_model_ids: set = None,
                     approval_context: dict = None) -> dict:
        """Delete a model from the pool. Conservative: blocks if active references exist.

        Args:
            exact_model_id: Model to delete
            force: Bypass recent/inactive usage warning (NOT active reference check)
            active_model_ids: Set of model IDs currently in active jobs (blocks delete)
            approval_context: Approval record (required for high-risk delete)

        Returns:
            dict with action, status, and audit info
        """
        if exact_model_id not in self.models:
            return {"error": f"model not found: {exact_model_id}",
                    "status": "blocked"}

        # Active reference check — cannot be bypassed even with force
        if active_model_ids and exact_model_id in active_model_ids:
            return {"error": f"model has active job reference: {exact_model_id}",
                    "status": "blocked",
                    "blocked_reason": "active_job_reference"}

        # High risk — requires approval
        if not approval_context:
            return {"action": "delete",
                    "model_id": exact_model_id,
                    "status": "approval_required",
                    "risk_level": "high",
                    "requires_approval": True}

        # Remove from pool
        del self.models[exact_model_id]
        self.save()
        return {"action": "deleted",
                "exact_model_id": exact_model_id,
                "status": "executed",
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

    # --- V1.21.7: Fuzzy Alias Resolution ---

    def seed_known_models(self, nodes: list = None, save: bool = True) -> dict:
        """Seed pool with KNOWN_MODELS_SEED when no snapshot exists.

        Does NOT overwrite existing models. Only adds missing entries.
        Node availability set to 'configured' (static, not live-verified).

        Args:
            nodes: Node list for availability (default: 5bao, 9bao, 21bao).
            save: If True, persist to disk. If False, in-memory only (read-only).
        """
        if nodes is None:
            nodes = ["5bao", "9bao", "21bao"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        added = []
        for seed in KNOWN_MODELS_SEED:
            mid = seed["exact_model_id"]
            if mid in self.models:
                continue
            entry = new_model_entry(
                mid,
                alias=seed.get("alias", ""),
                cost_tag=seed.get("cost_tag", "unknown"),
                roles=seed.get("roles", []),
                capability_tags=seed.get("capability_tags", []),
                source_flags=seed.get("source_flags", []),
            )
            entry["display_name"] = seed.get("display_name", "")
            entry["priority"] = seed.get("priority", 10)
            entry["lifecycle_status"] = "enabled"
            entry["last_seen"] = now
            entry["health_status"] = "configured"
            # Set quarantine if known
            if mid in KNOWN_QUARANTINE:
                entry["quarantine_status"] = "quarantined"
                entry["quarantine_reason"] = KNOWN_QUARANTINE[mid]
            else:
                entry["quarantine_status"] = "none"
                entry["quarantine_reason"] = None
            # Node availability: mark as 'configured' (not live-verified)
            for node in nodes:
                entry["node_availability"][node] = {
                    "available": True,
                    "last_seen": now,
                    "status": "configured",
                }
            entry["recommended_roles"] = seed.get("recommended_roles", [])
            entry["data_source"] = "static_seed"
            self.models[mid] = entry
            added.append(mid)
        if added:
            self.snapshot_timestamp = now
            if save:
                self.save()
        return {
            "action": "seeded",
            "added": sorted(added),
            "total": len(self.models),
            "snapshot_sha256": self.snapshot_sha256,
            "note": "static/configured — run discover --all for live node availability",
        }

    def resolve_fuzzy_alias(self, alias: str, node_id: str = None) -> dict:
        """Resolve a potentially fuzzy/ambiguous alias to model candidates.

        Returns:
            {
                "alias": str,
                "matched": bool,
                "ambiguous": bool,
                "candidates": [{exact_model_id, display_name, cost_tag,
                                quarantine_status, selectable, provider}],
                "exact_match": str or None,  # set only when unambiguous
                "requires_operator_confirmation": bool,
                "message": str,
            }
        """
        # Auto-seed if pool is empty (in-memory only, no disk write)
        if not self.models:
            self.seed_known_models(save=False)

        normalized = alias.strip().lower()

        # Step 1: Check exact alias map (case-insensitive)
        for known_alias, model_id in EXACT_ALIAS_MAP.items():
            if known_alias.lower() == normalized:
                return self._build_alias_result(
                    alias, model_id, ambiguous=False,
                    message=f"Exact match: {model_id}",
                )

        # Step 2: Check exact_model_id direct match
        for mid in self.models:
            if mid.lower() == normalized:
                return self._build_alias_result(
                    alias, mid, ambiguous=False,
                    message=f"Direct model ID match: {mid}",
                )

        # Step 3: Check ambiguous alias map
        for known_alias, candidates in AMBIGUOUS_ALIAS_MAP.items():
            if known_alias.lower() == normalized:
                return self._build_ambiguous_result(alias, candidates,
                    message=f"Ambiguous alias '{alias}' — operator must choose")

        # Step 4: Fuzzy substring match against all model IDs and aliases
        fuzzy_candidates = []
        for mid, entry in self.models.items():
            mid_lower = mid.lower()
            entry_alias = entry.get("alias", "").lower()
            display = entry.get("display_name", "").lower()
            if (normalized in mid_lower or
                normalized in entry_alias or
                normalized in display):
                fuzzy_candidates.append(mid)

        if len(fuzzy_candidates) == 1:
            return self._build_alias_result(
                alias, fuzzy_candidates[0], ambiguous=False,
                message=f"Fuzzy match: {fuzzy_candidates[0]}",
            )
        elif len(fuzzy_candidates) > 1:
            return self._build_ambiguous_result(alias, fuzzy_candidates,
                message=f"Fuzzy match returned {len(fuzzy_candidates)} candidates — operator must choose")

        # Step 5: No match at all
        all_ids = sorted(self.models.keys())
        return {
            "alias": alias,
            "matched": False,
            "ambiguous": False,
            "candidates": [],
            "exact_match": None,
            "requires_operator_confirmation": True,
            "message": f"No match for '{alias}'. Available models: {', '.join(all_ids)}",
            "available_models": all_ids,
        }

    def _build_alias_result(self, alias: str, model_id: str,
                            ambiguous: bool, message: str) -> dict:
        """Build result for a single matched alias."""
        entry = self.models.get(model_id, {})
        is_quarantined = entry.get("quarantine_status") == "quarantined"
        selectable = (
            entry.get("enabled", True) and
            entry.get("lifecycle_status", "enabled") == "enabled" and
            not is_quarantined
        )
        non_selectable_reason = None
        if not selectable:
            reasons = []
            if not entry.get("enabled", True):
                reasons.append("disabled")
            if entry.get("lifecycle_status") in ("disabled", "retired"):
                reasons.append(f"lifecycle={entry['lifecycle_status']}")
            if is_quarantined:
                q_reason = entry.get("quarantine_reason") or "unknown"
                reasons.append(f"quarantined: {q_reason}")
            non_selectable_reason = "; ".join(reasons) if reasons else "unknown"

        return {
            "alias": alias,
            "matched": True,
            "ambiguous": ambiguous,
            "candidates": [self._model_candidate_entry(model_id, entry)],
            "exact_match": model_id if not ambiguous else None,
            "requires_operator_confirmation": ambiguous or not selectable,
            "message": message,
        }

    def _build_ambiguous_result(self, alias: str, candidate_ids: list,
                                message: str) -> dict:
        """Build result for ambiguous alias."""
        candidates = []
        for mid in candidate_ids:
            entry = self.models.get(mid, {})
            candidates.append(self._model_candidate_entry(mid, entry))
        return {
            "alias": alias,
            "matched": True,
            "ambiguous": True,
            "candidates": candidates,
            "exact_match": None,
            "requires_operator_confirmation": True,
            "message": message,
        }

    def _model_candidate_entry(self, model_id: str, entry: dict) -> dict:
        """Build a single candidate entry for alias resolution output."""
        is_quarantined = entry.get("quarantine_status") == "quarantined"
        selectable = (
            entry.get("enabled", True) and
            entry.get("lifecycle_status", "enabled") == "enabled" and
            not is_quarantined
        )
        non_selectable_reason = None
        if not selectable:
            reasons = []
            if not entry.get("enabled", True):
                reasons.append("disabled")
            if entry.get("lifecycle_status") in ("disabled", "retired"):
                reasons.append(f"lifecycle={entry['lifecycle_status']}")
            if is_quarantined:
                q_reason = entry.get("quarantine_reason") or "unknown"
                reasons.append(f"quarantined: {q_reason}")
            non_selectable_reason = "; ".join(reasons) if reasons else "unknown"

        return {
            "exact_model_id": model_id,
            "display_name": entry.get("display_name", model_id),
            "provider": entry.get("provider", "unknown"),
            "cost_tag": entry.get("cost_tag", "unknown"),
            "selectable": selectable,
            "non_selectable_reason": non_selectable_reason,
            "quarantine_status": entry.get("quarantine_status",
                                           "quarantined" if is_quarantined else "none"),
            "quarantine_reason": entry.get("quarantine_reason"),
            "recommended_roles": entry.get("recommended_roles", []),
        }

    def operator_table(self, nodes: list = None) -> dict:
        """Generate operator-facing model pool table.

        Returns complete model pool with all required fields for
        operator decision-making.
        """
        if nodes is None:
            nodes = ["5bao", "9bao", "21bao"]

        # Auto-seed if pool is empty (in-memory only, no disk write)
        if not self.models:
            self.seed_known_models(nodes=nodes, save=False)

        table = []
        for mid in sorted(self.models.keys()):
            entry = self.models[mid]

            # Quarantine status
            is_quarantined = entry.get("quarantine_status") == "quarantined"
            quarantine_status = "quarantined" if is_quarantined else "none"
            quarantine_reason = entry.get("quarantine_reason") if is_quarantined else None

            # Selectability
            selectable = (
                entry.get("enabled", True) and
                entry.get("lifecycle_status", "enabled") == "enabled" and
                not is_quarantined
            )
            non_selectable_reason = None
            if not selectable:
                reasons = []
                if not entry.get("enabled", True):
                    reasons.append("disabled")
                if entry.get("lifecycle_status") in ("disabled", "retired"):
                    reasons.append(f"lifecycle={entry['lifecycle_status']}")
                if is_quarantined:
                    reasons.append(f"quarantined: {quarantine_reason}")
                non_selectable_reason = "; ".join(reasons) if reasons else "unknown"

            # Node availability
            node_avail = {}
            for node in nodes:
                avail_info = entry.get("node_availability", {}).get(node, {})
                node_avail[node] = {
                    "available": avail_info.get("available", False),
                    "status": avail_info.get("status", "unknown"),
                    "last_seen": avail_info.get("last_seen"),
                }

            # Source
            source_flags = entry.get("source_flags", [])
            if "user_configured" in source_flags and "opencode_discovered" in source_flags:
                source = "user_configured+opencode_discovered"
            elif "user_configured" in source_flags:
                source = "user_configured"
            elif "opencode_discovered" in source_flags:
                source = "opencode_discovered"
            else:
                source = "unknown"

            # Ambiguity notes
            ambiguity_notes = []
            # Check if alias conflicts with other models
            alias = entry.get("alias", "")
            for other_mid, other_entry in self.models.items():
                if other_mid == mid:
                    continue
                other_alias = other_entry.get("alias", "")
                # Same prefix ambiguity
                if (alias and other_alias and
                    alias.split("-")[0] == other_alias.split("-")[0] and
                    alias.split("-")[0] in ("mimo", "deepseek")):
                    note = f"alias '{alias}' may be confused with '{other_alias}' ({other_mid})"
                    if note not in ambiguity_notes:
                        ambiguity_notes.append(note)

            # Live validation status
            live_val = entry.get("live_validation", {})
            live_validation_status = "unknown"
            if live_val.get("validated"):
                live_validation_status = f"validated (verdict={live_val.get('last_verdict', '?')})"
            elif entry.get("data_source") == "static_seed":
                live_validation_status = "static/configured"
            elif entry.get("health_status") == "configured":
                live_validation_status = "static/configured"

            table.append({
                "exact_model_id": mid,
                "aliases": [alias] if alias else [],
                "display_name": entry.get("display_name", ""),
                "provider": entry.get("provider", "unknown"),
                "cost_tag": entry.get("cost_tag", "unknown"),
                "source": source,
                "node_availability": node_avail,
                "live_validation_status": live_validation_status,
                "quarantine_status": quarantine_status,
                "quarantine_reason": quarantine_reason,
                "recommended_roles": entry.get("recommended_roles", []),
                "ambiguity_notes": ambiguity_notes,
                "selectable": selectable,
                "non_selectable_reason": non_selectable_reason,
                "lifecycle_status": entry.get("lifecycle_status", "enabled"),
                "priority": entry.get("priority", 10),
            })

        return {
            "version": __version__,
            "table_version": "1.21.7",
            "generated_at": self.snapshot_timestamp,
            "snapshot_sha256": self.snapshot_sha256,
            "model_count": len(table),
            "selectable_count": sum(1 for r in table if r["selectable"]),
            "quarantined_count": sum(1 for r in table if r["quarantine_status"] == "quarantined"),
            "data_source": "static_seed" if not self.models else "pool",
            "note": ("node availability is static/configured — "
                     "run 'discover --all' for live 33/33 verification"),
            "nodes": nodes,
            "table": table,
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

        # --- V1.21.7: Fuzzy Alias Resolution self-checks ---

        # sc-46: seed_known_models on empty pool
        pool_seed = ModelPool("/tmp/test_pool_seed.json")
        seed_result = pool_seed.seed_known_models(nodes=["5bao", "9bao", "21bao"])
        check("sc-46-seed-count", seed_result["total"] == 11,
              f"total={seed_result['total']}")
        check("sc-46-seed-11-added", len(seed_result["added"]) == 11,
              f"added={len(seed_result['added'])}")

        # sc-47: seeded models have quarantine_status field
        ark = pool_seed.models.get("volcengine-plan/ark-code-latest", {})
        check("sc-47-ark-quarantined", ark.get("quarantine_status") == "quarantined",
              f"status={ark.get('quarantine_status')}")
        check("sc-47-ark-quarantine-reason",
              ark.get("quarantine_reason") == "key_format_incorrect",
              f"reason={ark.get('quarantine_reason')}")

        # sc-48: non-quarantined model has quarantine_status=none
        ds_flash = pool_seed.models.get("deepseek-plan/deepseek-v4-flash", {})
        check("sc-48-non-quarantine", ds_flash.get("quarantine_status") == "none")

        # sc-49: seeded models have node_availability with status=configured
        check("sc-49-node-avail-configured",
              ds_flash.get("node_availability", {}).get("5bao", {}).get("status") == "configured")

        # sc-50: resolve exact alias "doubao"
        r_doubao = pool_seed.resolve_fuzzy_alias("doubao")
        check("sc-50-doubao-matched", r_doubao["matched"])
        check("sc-50-doubao-exact", r_doubao["exact_match"] == "volcengine-plan/ark-code-latest")
        check("sc-50-doubao-not-ambiguous", not r_doubao["ambiguous"])
        check("sc-50-doubao-not-selectable",
              not r_doubao["candidates"][0]["selectable"])
        check("sc-50-doubao-quarantine",
              "quarantined" in (r_doubao["candidates"][0]["non_selectable_reason"] or ""),
              f"reason={r_doubao['candidates'][0]['non_selectable_reason']}")
        check("sc-50-doubao-requires-confirmation",
              r_doubao["requires_operator_confirmation"])

        # sc-51: resolve "deepseek pro" → unique
        r_ds_pro = pool_seed.resolve_fuzzy_alias("deepseek pro")
        check("sc-51-ds-pro-matched", r_ds_pro["matched"])
        check("sc-51-ds-pro-exact", r_ds_pro["exact_match"] == "deepseek-plan/deepseek-v4-pro")
        check("sc-51-ds-pro-not-ambiguous", not r_ds_pro["ambiguous"])
        check("sc-51-ds-pro-selectable", r_ds_pro["candidates"][0]["selectable"])

        # sc-52: resolve "deepseek flash" → unique
        r_ds_flash = pool_seed.resolve_fuzzy_alias("deepseek flash")
        check("sc-52-ds-flash-matched", r_ds_flash["matched"])
        check("sc-52-ds-flash-exact", r_ds_flash["exact_match"] == "deepseek-plan/deepseek-v4-flash")
        check("sc-52-ds-flash-not-ambiguous", not r_ds_flash["ambiguous"])

        # sc-53: resolve "mimo pro" → unique
        r_mimo_pro = pool_seed.resolve_fuzzy_alias("mimo pro")
        check("sc-53-mimo-pro-matched", r_mimo_pro["matched"])
        check("sc-53-mimo-pro-exact", r_mimo_pro["exact_match"] == "xiaomi-plan/mimo-v2.5-pro")
        check("sc-53-mimo-pro-not-ambiguous", not r_mimo_pro["ambiguous"])

        # sc-54: resolve "mimo" → ambiguous
        r_mimo = pool_seed.resolve_fuzzy_alias("mimo")
        check("sc-54-mimo-matched", r_mimo["matched"])
        check("sc-54-mimo-ambiguous", r_mimo["ambiguous"])
        check("sc-54-mimo-3-candidates", len(r_mimo["candidates"]) >= 3,
              f"count={len(r_mimo['candidates'])}")
        check("sc-54-mimo-requires-confirmation", r_mimo["requires_operator_confirmation"])
        candidate_ids = [c["exact_model_id"] for c in r_mimo["candidates"]]
        check("sc-54-mimo-has-v25", "xiaomi-plan/mimo-v2.5" in candidate_ids)
        check("sc-54-mimo-has-v25-pro", "xiaomi-plan/mimo-v2.5-pro" in candidate_ids)
        check("sc-54-mimo-has-free", "opencode/mimo-v2.5-free" in candidate_ids)

        # sc-55: resolve "deepseek" → ambiguous
        r_ds = pool_seed.resolve_fuzzy_alias("deepseek")
        check("sc-55-ds-matched", r_ds["matched"])
        check("sc-55-ds-ambiguous", r_ds["ambiguous"])
        check("sc-55-ds-3-candidates", len(r_ds["candidates"]) >= 3,
              f"count={len(r_ds['candidates'])}")
        ds_ids = [c["exact_model_id"] for c in r_ds["candidates"]]
        check("sc-55-ds-has-flash", "deepseek-plan/deepseek-v4-flash" in ds_ids)
        check("sc-55-ds-has-pro", "deepseek-plan/deepseek-v4-pro" in ds_ids)
        check("sc-55-ds-has-free", "opencode/deepseek-v4-flash-free" in ds_ids)

        # sc-56: resolve unknown alias
        r_unknown = pool_seed.resolve_fuzzy_alias("gpt-4-turbo")
        check("sc-56-unknown-not-matched", not r_unknown["matched"])
        check("sc-56-unknown-requires-confirmation", r_unknown["requires_operator_confirmation"])
        check("sc-56-unknown-has-available-list", len(r_unknown.get("available_models", [])) > 0)

        # sc-57: resolve case-insensitive
        r_upper = pool_seed.resolve_fuzzy_alias("DOUBAO")
        check("sc-57-case-insensitive", r_upper["matched"])
        check("sc-57-case-exact", r_upper["exact_match"] == "volcengine-plan/ark-code-latest")

        # sc-58: operator_table
        tbl = pool_seed.operator_table()
        check("sc-58-table-count", tbl["model_count"] == 11,
              f"count={tbl['model_count']}")
        check("sc-58-table-version", tbl.get("table_version") == "1.21.7")
        check("sc-58-selectable-count", tbl["selectable_count"] == 10,
              f"selectable={tbl['selectable_count']}")
        check("sc-58-quarantined-count", tbl["quarantined_count"] == 1,
              f"quarantined={tbl['quarantined_count']}")

        # sc-59: operator_table fields completeness
        first_row = tbl["table"][0]
        required_fields = ["exact_model_id", "aliases", "provider", "cost_tag",
                           "source", "node_availability", "live_validation_status",
                           "quarantine_status", "quarantine_reason",
                           "recommended_roles", "ambiguity_notes",
                           "selectable", "non_selectable_reason"]
        missing_fields = [f for f in required_fields if f not in first_row]
        check("sc-59-table-fields", len(missing_fields) == 0,
              f"missing={missing_fields}")

        # sc-60: operator_table ark-code quarantined row
        ark_row = [r for r in tbl["table"] if r["exact_model_id"] == "volcengine-plan/ark-code-latest"]
        check("sc-60-ark-in-table", len(ark_row) == 1)
        if ark_row:
            check("sc-60-ark-not-selectable", not ark_row[0]["selectable"])
            check("sc-60-ark-quarantine-status", ark_row[0]["quarantine_status"] == "quarantined")
            check("sc-60-ark-quarantine-reason", ark_row[0]["quarantine_reason"] == "key_format_incorrect")

        # sc-61: operator_table ambiguity_notes populated for mimo/deepseek
        mimo_rows = [r for r in tbl["table"] if "mimo" in r["exact_model_id"].lower()
                     and r["exact_model_id"].startswith("xiaomi")]
        check("sc-61-mimo-ambiguity-notes",
              any(len(r["ambiguity_notes"]) > 0 for r in mimo_rows),
              f"notes={[r['ambiguity_notes'] for r in mimo_rows]}")

        # sc-62: resolve_alias CLI via operator_table auto-seeds
        pool_cli = ModelPool("/tmp/test_pool_cli.json")
        # Pool is empty, operator_table should auto-seed
        cli_tbl = pool_cli.operator_table()
        check("sc-62-auto-seed", cli_tbl["model_count"] == 11)

        # --- Issue #1 fix: KNOWN_QUARANTINE no longer permanently overrides ---

        # sc-63: seed quarantine then clear — selectable should recover
        pool_q = ModelPool("/tmp/test_pool_quarantine.json")
        pool_q.seed_known_models(save=False)
        # Verify initial quarantine
        ark_entry = pool_q.models.get("volcengine-plan/ark-code-latest", {})
        check("sc-63-initial-quarantine",
              ark_entry.get("quarantine_status") == "quarantined")
        # Clear quarantine (simulating discover/enable recovery)
        ark_entry["quarantine_status"] = "none"
        ark_entry["quarantine_reason"] = None
        # operator_table should now show selectable=true
        q_tbl = pool_q.operator_table()
        ark_row = [r for r in q_tbl["table"] if r["exact_model_id"] == "volcengine-plan/ark-code-latest"]
        if ark_row:
            check("sc-63-cleared-selectable", ark_row[0]["selectable"] is True)
            check("sc-63-cleared-quarantine-status", ark_row[0]["quarantine_status"] == "none")
            check("sc-63-cleared-quarantine-reason", ark_row[0]["quarantine_reason"] is None)
        else:
            check("sc-63-cleared-selectable", False, "ark-code-latest not in table")

        # sc-64: resolve-alias doubao after quarantine cleared
        r_doubao_cleared = pool_q.resolve_fuzzy_alias("doubao")
        check("sc-64-doubao-cleared-selectable",
              r_doubao_cleared["candidates"][0]["selectable"] is True)
        check("sc-64-doubao-cleared-confirm",
              r_doubao_cleared["requires_operator_confirmation"] is False)

        # sc-65: KNOWN_QUARANTINE constant still exists for seed (backward compat)
        check("sc-65-known-quarantine-exists",
              "volcengine-plan/ark-code-latest" in KNOWN_QUARANTINE)

        # --- Issue #2 fix: read-only commands don't write files ---

        # sc-66: operator-table on empty pool does NOT create file
        import tempfile
        tmpdir = tempfile.mkdtemp()
        pool_path_ro = os.path.join(tmpdir, "test_no_write.json")
        pool_ro = ModelPool(pool_path_ro)
        check("sc-66-pool-file-not-exist-before", not os.path.exists(pool_path_ro))
        _ = pool_ro.operator_table()
        check("sc-66-pool-file-not-exist-after", not os.path.exists(pool_path_ro),
              "operator-table should not write file")

        # sc-67: resolve-alias on empty pool does NOT create file
        pool_path_ro2 = os.path.join(tmpdir, "test_no_write2.json")
        pool_ro2 = ModelPool(pool_path_ro2)
        check("sc-67-pool-file-not-exist-before", not os.path.exists(pool_path_ro2))
        _ = pool_ro2.resolve_fuzzy_alias("doubao")
        check("sc-67-pool-file-not-exist-after", not os.path.exists(pool_path_ro2),
              "resolve-alias should not write file")

        # sc-68: explicit seed with save=True DOES create file
        pool_path_w = os.path.join(tmpdir, "test_write.json")
        pool_w = ModelPool(pool_path_w)
        pool_w.seed_known_models(save=True)
        check("sc-68-seed-save-creates-file", os.path.exists(pool_path_w))

        # Cleanup temp dir
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

        # Cleanup test pools
        for f in ["/tmp/test_pool_sc.json", "/tmp/test_pool_merge.json",
                   "/tmp/test_pool_mgmt.json", test_config_path,
                   "/tmp/test_pool_seed.json", "/tmp/test_pool_cli.json"]:
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

    # V1.21.7: resolve-alias (fuzzy)
    res_alias = sub.add_parser("resolve-alias")
    res_alias.add_argument("alias", help="Alias to resolve (fuzzy supported)")

    # V1.21.7: operator-table
    op_tbl = sub.add_parser("operator-table")
    op_tbl.add_argument("--nodes", nargs="+", default=["5bao", "9bao", "21bao"])

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

    elif args.command == "resolve-alias":
        result = pool.resolve_fuzzy_alias(args.alias)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "operator-table":
        result = pool.operator_table(nodes=args.nodes)
        print(json.dumps(result, indent=2, ensure_ascii=False))

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
