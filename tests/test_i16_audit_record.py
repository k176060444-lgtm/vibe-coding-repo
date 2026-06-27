#!/usr/bin/env python3
"""Tests for I16 runtime sync audit record integrity.

Verifies:
- Audit record exists and is parseable
- No real API keys or secret values in the audit record
- Extra visible models are not mislabeled as central pool models
- Route-all description matches actual route-all output
"""

import os
import re
import json
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
AUDIT_PATH = os.path.join(REPO_ROOT, "docs", "reports", "V1.21.33I16_RUNTIME_SYNC_AUDIT_RECORD.md")


def test_audit_record_exists():
    assert os.path.isfile(AUDIT_PATH), f"Audit record not found: {AUDIT_PATH}"


def test_audit_record_no_real_secrets():
    """Audit record must not contain real API keys, key prefixes, or key lengths."""
    with open(AUDIT_PATH) as f:
        content = f.read()

    # Check for real API key patterns (sk- followed by substantial alphanumeric)
    key_patterns = re.findall(r'sk-[a-zA-Z0-9]{10,}', content)
    assert len(key_patterns) == 0, f"Found potential API key patterns: {key_patterns[:3]}"

    # Check for AKIA patterns
    akia_patterns = re.findall(r'AKIA[0-9A-Z]{10,}', content)
    assert len(akia_patterns) == 0, f"Found AKIA patterns: {akia_patterns[:3]}"

    # Check no key lengths exposed (allow negation phrases like "NO key lengths")
    lines_with_key_length = [l.strip() for l in content.split('\n') if 'key length' in l.lower()]
    for line in lines_with_key_length:
        assert 'no' in line.lower() or 'not' in line.lower(), \
            f"Audit record contains non-negated key length reference: {line}"
    lines_with_key_prefix = [l.strip() for l in content.split('\n') if 'key prefix' in l.lower()]
    for line in lines_with_key_prefix:
        assert 'no' in line.lower() or 'not' in line.lower(), \
            f"Audit record contains non-negated key prefix reference: {line}"


def test_extra_models_not_mislabeled():
    """Extra visible models must be clearly marked as NOT in central pool."""
    with open(AUDIT_PATH) as f:
        content = f.read()

    extra_models = [
        "opencode-go/deepseek-v4-pro",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/minimax-m2.7",
        "opencode-go/minimax-m3",
        "opencode-go/qwen3.6-plus",
    ]

    # Find the "Extra Visible Models" section
    extra_section_start = content.find("### Extra Visible Models")
    assert extra_section_start >= 0, "Extra Visible Models section not found"

    extra_section = content[extra_section_start:]
    for model in extra_models:
        assert model in extra_section, f"Extra model {model} not documented in Extra Visible Models section"

    # Central pool section must NOT contain extra models
    central_section_start = content.find("### Central Pool")
    central_section_end = content.find("### Extra Visible Models")
    if central_section_start >= 0 and central_section_end > central_section_start:
        central_section = content[central_section_start:central_section_end]
        for model in extra_models:
            model_short = model.split("/")[-1]
            assert model_short not in central_section, f"Extra model {model_short} found in Central Pool section"


def test_route_all_unchanged_stated():
    """Audit record must state route-all 9 roles unchanged."""
    with open(AUDIT_PATH) as f:
        content = f.read()
    assert "9 roles unchanged" in content, "Route-all unchanged not stated in audit record"


def test_central_pool_8_models():
    """Audit record must list exactly 8 central pool opencode-go models."""
    with open(AUDIT_PATH) as f:
        content = f.read()

    central_section_start = content.find("### Central Pool")
    assert central_section_start >= 0, "Central Pool section not found"

    # Count model entries in central pool table (rows with `opencode-go-`)
    central_section = content[central_section_start:]
    model_entries = re.findall(r'opencode-go-\S+', central_section)
    assert len(model_entries) == 8, f"Expected 8 central pool models, found {len(model_entries)}: {model_entries}"


def test_route_all_matches_actual():
    """Verify route-all description in audit record matches actual route-all output."""
    result = subprocess.run(
        [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, f"route-all failed: {result.stderr}"
    routes = json.loads(result.stdout)

    with open(AUDIT_PATH) as f:
        content = f.read()

    for role, info in routes.items():
        model = info.get("recommended", "")
        assert model in content, f"Route-all role {role} -> {model} not found in audit record"


def test_no_secret_env_var_values():
    """Audit record must only reference env var names, not their values."""
    with open(AUDIT_PATH) as f:
        content = f.read()

    # Allowed env var name patterns
    allowed_refs = [
        "OPENCODE_GO_API_KEY",
        "OPENCODE_GO_BASE_URL",
        "VIBEDEB_VOLCENGINE_API_KEY",
        "VIBEDEB_DEEPSEEK_API_KEY",
        "VIBEDEB_MINIMAX_API_KEY",
        "VIBEDEB_XIAOMI_API_KEY",
    ]

    for ref in allowed_refs:
        # Check that the env var name appears, but not followed by a value
        occurrences = re.findall(rf'{re.escape(ref)}\S*', content)
        for occ in occurrences:
            # If it's just the name followed by punctuation or space, that's fine
            # If it has = followed by content, that's a problem
            if "=" in occ:
                # Allow {env:OPENCODE_GO_API_KEY} pattern
                if occ.startswith(ref + "="):
                    assert False, f"Env var {ref} appears with value assignment in audit record"
