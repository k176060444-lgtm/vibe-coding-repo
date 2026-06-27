#!/usr/bin/env python3
"""Tests for I17 opencode-go metadata alignment.

Verifies:
- All 8 opencode-go models have smoke_results=confirmed on 5bao/9bao
- smoke_required=false (already verified)
- health_status=ok
- enabled status unchanged (only canary enabled)
- Extra visible models still NOT in central pool
- Route-all unchanged
- Secret safety
"""

import os
import re
import yaml
import json
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
YAML_PATH = os.path.join(REPO_ROOT, "scripts", "model_pool.yaml")

OPCODE_GO_IDS = [
    "opencode-go-glm-5-2",
    "opencode-go-glm-5-1",
    "opencode-go-deepseek-v4-flash",
    "opencode-go-kimi-k2-6",
    "opencode-go-qwen3-7-max",
    "opencode-go-qwen3-7-plus",
    "opencode-go-mimo-v2-5-pro",
    "opencode-go-mimo-v2-5",
]

EXTRA_VISIBLE = [
    "opencode-go/deepseek-v4-pro",
    "opencode-go/kimi-k2.7-code",
    "opencode-go/minimax-m2.7",
    "opencode-go/minimax-m3",
    "opencode-go/qwen3.6-plus",
]


def load_pool():
    with open(YAML_PATH) as f:
        pool = yaml.safe_load(f)
    return pool


def test_8_opencode_go_models_present():
    pool = load_pool()
    go_models = [e for e in pool['models'] if e.get('provider') == 'opencode-go']
    assert len(go_models) == 8, f"Expected 8 opencode-go models, found {len(go_models)}"


def test_all_have_confirmed_smoke_results():
    pool = load_pool()
    for entry in pool['models']:
        if entry.get('provider') != 'opencode-go':
            continue
        eid = entry['id']
        sr = entry.get('smoke_results', {})
        for node in ['5bao', '9bao']:
            assert node in sr, f"{eid}: missing smoke_results for {node}"
            assert sr[node]['status'] == 'confirmed', \
                f"{eid}: {node} smoke status is {sr[node]['status']}, expected confirmed"
            assert sr[node]['smoke_phase'] == 'v1.21.33I16E_OPENCODE_GO_8_MODEL_DUAL_NODE_LIVE_SMOKE', \
                f"{eid}: {node} smoke_phase mismatch"
            assert sr[node]['wrapper'] == '~/bin/vibedev-opencode', \
                f"{eid}: {node} wrapper mismatch"
            assert 'opencode-go/' in sr[node]['invocation'], \
                f"{eid}: {node} invocation mismatch"


def test_smoke_required_false():
    pool = load_pool()
    for entry in pool['models']:
        if entry.get('provider') != 'opencode-go':
            continue
        assert entry.get('smoke_required') is False, \
            f"{entry['id']}: smoke_required should be False"
        assert entry.get('smoke_required') is not True, \
            f"{entry['id']}: smoke_required should not be True"


def test_health_status_ok():
    pool = load_pool()
    for entry in pool['models']:
        if entry.get('provider') != 'opencode-go':
            continue
        assert entry.get('health_status') == 'ok', \
            f"{entry['id']}: health_status should be 'ok', got {entry.get('health_status')}"


def test_enabled_status_unchanged():
    """Only opencode-go-deepseek-v4-flash (canary) should be enabled."""
    pool = load_pool()
    for entry in pool['models']:
        if entry.get('provider') != 'opencode-go':
            continue
        if entry['id'] == 'opencode-go-deepseek-v4-flash':
            assert entry.get('enabled') is True, f"Canary should be enabled"
        else:
            assert entry.get('enabled') is False, \
                f"{entry['id']} should NOT be enabled (I17 is metadata-only)"


def test_extra_visible_not_in_central_pool():
    """Extra visible models must NOT exist in model_pool.yaml."""
    pool = load_pool()
    pool_ids = [e.get('id', '') for e in pool['models']]
    for extra in EXTRA_VISIBLE:
        short = extra.split('/')[-1].replace('.', '-')
        # Check none of the pool IDs contain this model
        for pid in pool_ids:
            if short in pid and 'opencode-go' in pid:
                # This model should NOT be in the pool
                if 'opencode-go-' + short.replace('-pro', '-v4-pro' if 'v4' in short else short) in pool_ids:
                    pass  # Legitimate central pool model with similar name is ok
    # Just check the specific extra IDs aren't present
    for extra in EXTRA_VISIBLE:
        short = extra.split('/')[-1]
        # Convert to pool ID convention: dots to hyphens
        expected_id = f"opencode-go-{short.replace('.', '-')}"
        if expected_id == 'opencode-go-deepseek-v4-pro':
            assert expected_id not in pool_ids, \
                f"Extra model {expected_id} found in central pool!"
        elif expected_id == 'opencode-go-kimi-k2-7-code':
            assert expected_id not in pool_ids, \
                f"Extra model {expected_id} found in central pool!"
        elif expected_id == 'opencode-go-minimax-m2-7':
            assert expected_id not in pool_ids, \
                f"Extra model {expected_id} found in central pool!"
        elif expected_id == 'opencode-go-minimax-m3':
            assert expected_id not in pool_ids, \
                f"Extra model {expected_id} found in central pool!"
        elif expected_id == 'opencode-go-qwen3-6-plus':
            assert expected_id not in pool_ids, \
                f"Extra model {expected_id} found in central pool!"


def test_route_all_unchanged():
    """Route-all must still be 9 roles unchanged."""
    result = subprocess.run(
        [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, f"route-all failed: {result.stderr}"
    routes = json.loads(result.stdout)
    assert len(routes) == 9, f"Expected 9 roles, got {len(routes)}"
    # Check no opencode-go models in route-all
    for role, info in routes.items():
        model = info.get('recommended', '')
        assert 'opencode-go' not in model, \
            f"Route-all role {role} uses opencode-go model {model} (should be unchanged)"


def test_no_real_secrets_in_yaml():
    """model_pool.yaml must not contain real API keys."""
    with open(YAML_PATH) as f:
        content = f.read()
    key_patterns = re.findall(r'sk-[a-zA-Z0-9]{10,}', content)
    assert len(key_patterns) == 0, f"Found potential API key patterns: {key_patterns[:3]}"
    akia_patterns = re.findall(r'AKIA[0-9A-Z]{10,}', content)
    assert len(akia_patterns) == 0, f"Found AKIA patterns: {akia_patterns[:3]}"


def test_model_pool_self_check():
    """Self-check must still pass after metadata updates."""
    result = subprocess.run(
        [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, f"Self-check failed: {result.stderr}"
    assert '"passed": true' in result.stdout, "Self-check did not pass"
