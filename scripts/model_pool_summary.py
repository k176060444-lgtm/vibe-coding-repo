"""Summarize models from scripts/model_pool.yaml for a given provider.

This is a small read-only helper introduced for I11_OPENCODE_DS4FLASH_FIRST_REAL_SMALL_CODE_TASK.
It contains a single pure function `summarize_model` that converts a single
model_pool.yaml entry into a one-line human-readable summary string.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# Ensure project root is on sys.path so the third-party 'yaml' resolves
# from the project's venv when this script is invoked outside it.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml  # noqa: E402


def summarize_model(model_entry: Dict[str, Any]) -> str:
    """Return a short one-line summary of a single model_pool.yaml entry.

    Pure function. The output is deterministic and depends only on the input dict.
    """
    mid = model_entry.get("id", "unknown")
    provider = model_entry.get("provider", "unknown")
    name = model_entry.get("model", "unknown")
    cost = model_entry.get("cost", "unknown")
    enabled = bool(model_entry.get("enabled", False))
    priority = model_entry.get("priority", "N/A")
    fallback = model_entry.get("fallback_policy", "none")
    state = "enabled" if enabled else "disabled"
    return (
        f"{mid} | provider={provider} | model={name} | "
        f"cost={cost} | {state} | priority={priority} | fallback={fallback}"
    )


def summarize_opencode_models(yaml_path: Path | None = None) -> list[str]:
    """Read model_pool.yaml and return summaries for all opencode-go models.

    Returns an empty list when the file is missing or has no opencode-go entries.
    """
    yaml_path = yaml_path or (Path(__file__).resolve().parent / "model_pool.yaml")
    if not yaml_path.exists():
        return []
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [
        summarize_model(m)
        for m in (data.get("models") or [])
        if isinstance(m, dict) and m.get("provider") == "opencode-go"
    ]


if __name__ == "__main__":
    for line in summarize_opencode_models():
        print(line)
