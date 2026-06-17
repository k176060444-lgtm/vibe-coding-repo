#!/usr/bin/env python3
"""vibe_model_health.py — Model Health Registry v1.0.0

Tracks provider/model availability status for the worker pool scheduler.
Models with authentication or connectivity issues are quarantined.

Usage:
    python3 scripts/vibe_model_health.py --status
    python3 scripts/vibe_model_health.py --check --model deepseek-plan/deepseek-v4-flash
    python3 scripts/vibe_model_health.py --self-check
"""

__version__ = "1.0.0"

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ModelStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED_AUTH = "DEGRADED_AUTH"
    DEGRADED_RATE = "DEGRADED_RATE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ModelHealth:
    provider: str
    model_alias: str
    status: ModelStatus = ModelStatus.UNKNOWN
    health_reason: str = ""
    affected_workers: list = field(default_factory=list)
    last_check: str = ""
    last_success: str = ""
    consecutive_failures: int = 0


# Known models and their initial health status
KNOWN_MODELS = {
    "deepseek-plan/deepseek-v4-flash": ModelHealth(
        provider="deepseek-plan", model_alias="deepseek-v4-flash",
        status=ModelStatus.AVAILABLE,
    ),
    "deepseek-plan/deepseek-v4-pro": ModelHealth(
        provider="deepseek-plan", model_alias="deepseek-v4-pro",
        status=ModelStatus.AVAILABLE,
    ),
    "volcengine-plan/ark-code-latest": ModelHealth(
        provider="volcengine-plan", model_alias="ark-code-latest",
        status=ModelStatus.DEGRADED_AUTH,
        health_reason="key_format_incorrect",
        affected_workers=["5bao", "9bao"],
    ),
    "xiaomi-plan/mimo-v2.5": ModelHealth(
        provider="xiaomi-plan", model_alias="mimo-v2.5",
        status=ModelStatus.AVAILABLE,
    ),
    "xiaomi-plan/mimo-v2.5-pro": ModelHealth(
        provider="xiaomi-plan", model_alias="mimo-v2.5-pro",
        status=ModelStatus.AVAILABLE,
    ),
    "minimax-plan/MiniMax-M3": ModelHealth(
        provider="minimax-plan", model_alias="MiniMax-M3",
        status=ModelStatus.AVAILABLE,
    ),
}


class ModelHealthRegistry:
    """Registry tracking model health status."""

    def __init__(self):
        self.models: dict[str, ModelHealth] = dict(KNOWN_MODELS)

    def get_status(self, provider_model: str) -> ModelHealth:
        return self.models.get(provider_model, ModelHealth(
            provider=provider_model.split("/")[0] if "/" in provider_model else "unknown",
            model_alias=provider_model.split("/")[-1] if "/" in provider_model else provider_model,
            status=ModelStatus.UNKNOWN,
            health_reason="not_in_registry",
        ))

    def is_available(self, provider_model: str) -> bool:
        h = self.get_status(provider_model)
        return h.status == ModelStatus.AVAILABLE

    def list_available(self) -> list[str]:
        return [k for k, v in self.models.items() if v.status == ModelStatus.AVAILABLE]

    def list_quarantined(self) -> list[str]:
        return [k for k, v in self.models.items() if v.status != ModelStatus.AVAILABLE]

    def set_status(self, provider_model: str, status: ModelStatus,
                   reason: str = "", workers: list = None):
        if provider_model in self.models:
            self.models[provider_model].status = status
            self.models[provider_model].health_reason = reason
            if workers:
                self.models[provider_model].affected_workers = workers
            self.models[provider_model].last_check = datetime.now(timezone.utc).isoformat()
            if status == ModelStatus.AVAILABLE:
                self.models[provider_model].consecutive_failures = 0
                self.models[provider_model].last_success = self.models[provider_model].last_check
            else:
                self.models[provider_model].consecutive_failures += 1

    def status_report(self) -> dict:
        return {
            "total": len(self.models),
            "available": len(self.list_available()),
            "quarantined": len(self.list_quarantined()),
            "models": {k: asdict(v) for k, v in self.models.items()},
        }


def self_check() -> dict:
    """Run self-check."""
    reg = ModelHealthRegistry()
    checks = []

    checks.append({"name": "version", "passed": True, "message": __version__})
    checks.append({"name": "registry_loads", "passed": len(reg.models) == 6,
                    "message": f"models={len(reg.models)}"})
    checks.append({"name": "available_count", "passed": len(reg.list_available()) == 5,
                    "message": f"available={len(reg.list_available())}"})
    checks.append({"name": "quarantined_count", "passed": len(reg.list_quarantined()) == 1,
                    "message": f"quarantined={len(reg.list_quarantined())}"})
    checks.append({"name": "ark_quarantined",
                    "passed": not reg.is_available("volcengine-plan/ark-code-latest"),
                    "message": "ark-code-latest=DEGRADED_AUTH"})
    checks.append({"name": "deepseek_available",
                    "passed": reg.is_available("deepseek-plan/deepseek-v4-flash"),
                    "message": "deepseek-v4-flash=AVAILABLE"})
    checks.append({"name": "quarantine_reason",
                    "passed": reg.get_status("volcengine-plan/ark-code-latest").health_reason == "key_format_incorrect",
                    "message": "reason=key_format_incorrect"})
    checks.append({"name": "affected_workers",
                    "passed": set(reg.get_status("volcengine-plan/ark-code-latest").affected_workers) == {"5bao", "9bao"},
                    "message": "affected=5bao,9bao"})

    passed = sum(1 for c in checks if c["passed"])
    return {"overall": "PASS" if passed == len(checks) else "FAIL",
            "passed": passed, "total": len(checks), "checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Model Health Registry")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check", metavar="PROVIDER/MODEL")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reg = ModelHealthRegistry()

    if args.self_check:
        r = self_check()
    elif args.check:
        h = reg.get_status(args.check)
        r = asdict(h)
    elif args.status:
        r = reg.status_report()
    else:
        r = reg.status_report()

    if args.json or args.self_check:
        print(json.dumps(r, indent=2))
    else:
        if "models" in r:
            for k, v in r["models"].items():
                s = v["status"]
                reason = f" ({v['health_reason']})" if v["health_reason"] else ""
                print(f"  {k}: {s}{reason}")
        else:
            print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
