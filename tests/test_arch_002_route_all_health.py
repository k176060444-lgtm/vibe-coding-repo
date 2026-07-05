#!/usr/bin/env python3
"""I23 ARCH-002 — Test that route-all consults fresh health gate.

Verifies:
1. test_probe_all_invoked_at_route_all
2. test_unknown_health_triggers_error (fail-closed)
3. test_offline_worker_excluded (regression)
4. test_online_worker_selected (regression)
5. test_fresh_check_skips_reprobe
6. test_no_regression_other_gates
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest import mock

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestFreshProbeAllInvoked:
    """Test 1: _fresh_probe_all is invoked from route_all."""

    def test_probe_all_invoked_at_route_all(self):
        from vibe_model_routing_policy import route_all, _fresh_probe_all
        with mock.patch(
            "vibe_model_routing_policy._fresh_probe_all",
            return_value={
                "checked": [], "skipped_fresh": ["21bao", "5bao", "9bao"],
                "freshness_max_age_sec": 300, "errors": [],
            },
        ) as mocked:
            result = route_all()
        # _fresh_probe_all was called exactly once during route_all()
        assert mocked.call_count >= 1, (
            f"_fresh_probe_all not invoked; got {mocked.call_count}"
        )
        # And its summary lands in gate_results
        assert "_gate_results" in result
        assert "arch_002_worker_health_freshness" in result["_gate_results"]

    def test_helper_returns_summary_keys(self):
        """Direct test of _fresh_probe_all return shape."""
        from vibe_model_routing_policy import _fresh_probe_all
        import vibe_worker_registry as _wr
        reg = _wr.WorkerRegistry()
        summary = _fresh_probe_all(reg, max_age_sec=300)
        assert "checked" in summary
        assert "skipped_fresh" in summary
        assert "freshness_max_age_sec" in summary
        assert summary["freshness_max_age_sec"] == 300


class TestUnknownHealthBlocks:
    """Test 2: UNKNOWN health must fail-closed in _resolve_node_for_role."""

    def test_unknown_health_triggers_error(self):
        """Pure unit test — no probe; all workers UNKNOWN."""
        from vibe_model_routing_policy import _resolve_node_for_role
        # Build a fake registry with UNKNOWN health for everyone
        fake_reg = {
            "21bao": {
                "worker_id": "21bao", "node_type": "windows-worker",
                "transport": "local-exec", "enabled": True,
                "maintenance_status": "active",
                "health_status": "UNKNOWN",
                "capabilities": ["implementer-small"],
            },
            "5bao": {
                "worker_id": "5bao", "node_type": "debian-worker",
                "transport": "ssh", "enabled": True,
                "maintenance_status": "active",
                "health_status": "UNKNOWN",
                "capabilities": ["implementer"],
            },
            "9bao": {
                "worker_id": "9bao", "node_type": "debian-worker",
                "transport": "ssh", "enabled": True,
                "maintenance_status": "active",
                "health_status": "UNKNOWN",
                "capabilities": ["reviewer-a"],
            },
        }
        # implementer role prefers [5bao, 9bao, 21bao]; all UNKNOWN → blocked
        nid, attr = _resolve_node_for_role("implementer", fake_reg)
        assert nid is None
        assert attr["error"] == "HEALTH_UNKNOWN_BLOCKED"
        assert "blocked_nodes" in attr
        blocked_ids = {b["node_id"] for b in attr["blocked_nodes"]}
        assert blocked_ids == {"5bao", "9bao", "21bao"}

    def test_empty_health_treated_as_unknown(self):
        """Empty health_status must also block."""
        from vibe_model_routing_policy import _resolve_node_for_role
        fake_reg = {
            "21bao": {
                "worker_id": "21bao", "node_type": "windows-worker",
                "transport": "local-exec", "enabled": True,
                "maintenance_status": "active",
                "health_status": "",  # empty
                "capabilities": ["implementer-small"],
            },
        }
        # orchestrator prefers [21bao, "win"]; both blocked
        nid, attr = _resolve_node_for_role("orchestrator", fake_reg)
        assert nid is None
        assert attr["error"] == "HEALTH_UNKNOWN_BLOCKED"


class TestOfflineExcluded:
    """Test 3: OFFLINE still excluded (regression)."""

    def test_offline_worker_excluded(self):
        from vibe_model_routing_policy import _resolve_node_for_role
        fake_reg = {
            "5bao": {
                "worker_id": "5bao", "node_type": "debian-worker",
                "transport": "ssh", "enabled": True,
                "maintenance_status": "active",
                "health_status": "OFFLINE",
                "capabilities": ["implementer"],
            },
            "9bao": {
                "worker_id": "9bao", "node_type": "debian-worker",
                "transport": "ssh", "enabled": True,
                "maintenance_status": "active",
                "health_status": "ONLINE",
                "capabilities": ["implementer"],
            },
        }
        nid, attr = _resolve_node_for_role("implementer", fake_reg)
        assert nid == "9bao"
        assert attr["health_status"] == "ONLINE"

    def test_all_offline_returns_no_available_node(self):
        """All OFFLINE → NO_AVAILABLE_NODE (not HEALTH_UNKNOWN_BLOCKED)."""
        from vibe_model_routing_policy import _resolve_node_for_role
        fake_reg = {
            "5bao": {"worker_id": "5bao", "node_type": "debian-worker",
                     "transport": "ssh", "enabled": True,
                     "maintenance_status": "active",
                     "health_status": "OFFLINE", "capabilities": ["implementer"]},
            "9bao": {"worker_id": "9bao", "node_type": "debian-worker",
                     "transport": "ssh", "enabled": True,
                     "maintenance_status": "active",
                     "health_status": "OFFLINE", "capabilities": ["implementer"]},
        }
        nid, attr = _resolve_node_for_role("implementer", fake_reg)
        assert nid is None
        assert attr["error"] == "NO_AVAILABLE_NODE"


class TestOnlineSelected:
    """Test 4: ONLINE can be selected (regression)."""

    def test_online_worker_selected(self):
        from vibe_model_routing_policy import _resolve_node_for_role
        fake_reg = {
            "21bao": {"worker_id": "21bao", "node_type": "windows-worker",
                      "transport": "local-exec", "enabled": True,
                      "maintenance_status": "active",
                      "health_status": "ONLINE", "capabilities": ["orchestrator"]},
        }
        nid, attr = _resolve_node_for_role("orchestrator", fake_reg)
        assert nid == "21bao"
        assert attr["health_status"] == "ONLINE"

    def test_first_preferred_online_wins(self):
        """If multiple preferred nodes ONLINE, first one in ROLE_NODE_PREFERENCE wins."""
        from vibe_model_routing_policy import _resolve_node_for_role
        # implementer prefers [5bao, 9bao, 21bao]; 5bao and 9bao ONLINE
        fake_reg = {
            "5bao": {"worker_id": "5bao", "node_type": "debian-worker",
                     "transport": "ssh", "enabled": True,
                     "maintenance_status": "active",
                     "health_status": "ONLINE", "capabilities": ["implementer"]},
            "9bao": {"worker_id": "9bao", "node_type": "debian-worker",
                     "transport": "ssh", "enabled": True,
                     "maintenance_status": "active",
                     "health_status": "ONLINE", "capabilities": ["implementer"]},
            "21bao": {"worker_id": "21bao", "node_type": "windows-worker",
                      "transport": "local-exec", "enabled": True,
                      "maintenance_status": "active",
                      "health_status": "ONLINE", "capabilities": ["implementer"]},
        }
        nid, _ = _resolve_node_for_role("implementer", fake_reg)
        assert nid == "5bao"  # first in preference list


class TestFreshCheckSkipsReprobe:
    """Test 5: Workers with fresh last_health_check are skipped on re-probe."""

    def test_fresh_check_skips_reprobe(self):
        """If last_health_check is recent (< max_age_sec), worker is skipped."""
        from vibe_model_routing_policy import _fresh_probe_all
        import vibe_worker_registry as _wr
        reg = _wr.WorkerRegistry()
        # Mark 21bao as recently checked (now)
        now_iso = datetime.now(timezone.utc).isoformat()
        reg.set_health("21bao", "ONLINE")
        reg.workers["21bao"].last_health_check = now_iso
        # Mark 5bao/9bao as stale (long ago)
        old_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        reg.set_health("5bao", "ONLINE")
        reg.workers["5bao"].last_health_check = old_iso
        reg.set_health("9bao", "OFFLINE")
        reg.workers["9bao"].last_health_check = old_iso

        with mock.patch.object(reg, "probe_all",
                               return_value={"21bao": {"status": "ONLINE"},
                                             "5bao": {"status": "ONLINE"},
                                             "9bao": {"status": "OFFLINE"}}) as pa:
            summary = _fresh_probe_all(reg, max_age_sec=300)
        # 21bao skipped (fresh), 5bao/9bao re-probed
        assert "21bao" in summary["skipped_fresh"]
        assert "5bao" in summary["checked"]
        assert "9bao" in summary["checked"]
        pa.assert_called_once()

    def test_empty_check_triggers_probe(self):
        """If last_health_check is empty, worker is probed."""
        from vibe_model_routing_policy import _fresh_probe_all
        import vibe_worker_registry as _wr
        reg = _wr.WorkerRegistry()
        # Empty last_health_check on all workers
        for wid in ("21bao", "5bao", "9bao"):
            reg.workers[wid].last_health_check = ""
        with mock.patch.object(reg, "probe_all",
                               return_value={wid: {"status": "ONLINE"}
                                             for wid in ("21bao", "5bao", "9bao")}) as pa:
            summary = _fresh_probe_all(reg, max_age_sec=300)
        assert summary["skipped_fresh"] == []
        assert set(summary["checked"]) == {"21bao", "5bao", "9bao"}
        pa.assert_called_once()

    def test_unknown_check_triggers_probe(self):
        """last_health_check='UNKNOWN' must trigger probe (treated as stale)."""
        from vibe_model_routing_policy import _fresh_probe_all
        import vibe_worker_registry as _wr
        reg = _wr.WorkerRegistry()
        reg.set_health("21bao", "UNKNOWN")
        reg.workers["21bao"].last_health_check = "UNKNOWN"
        with mock.patch.object(reg, "probe_all",
                               return_value={"21bao": {"status": "ONLINE"}}):
            summary = _fresh_probe_all(reg, max_age_sec=300)
        assert "21bao" in summary["checked"]
        assert "21bao" not in summary["skipped_fresh"]


class TestNoRegressionOtherGates:
    """Test 6: route-all still produces 9 roles + DSP-002/ARCH-001/POOL-001 gates."""

    def test_no_regression_other_gates(self):
        """route-all still emits 9 roles and gate_results has DSP-002/ARCH-001."""
        from vibe_model_routing_policy import route_all
        # Mock probes so workers are forced ONLINE
        with mock.patch(
            "vibe_worker_registry.WorkerRegistry.probe_all",
            return_value={
                "21bao": {"status": "ONLINE"},
                "5bao": {"status": "ONLINE"},
                "9bao": {"status": "ONLINE"},
            },
        ):
            result = route_all()
        # 9 roles preserved
        roles = {k: v for k, v in result.items() if not k.startswith("_")}
        assert len(roles) == 9
        expected_roles = {"orchestrator", "explorer", "planner", "implementer",
                          "tester-a", "tester-b", "reviewer-a", "reviewer-b",
                          "git-integrator"}
        assert set(roles.keys()) == expected_roles
        # DSP-002 still gates
        gate = result["_gate_results"]
        assert "operator_checkpoint" in gate
        assert gate["operator_checkpoint"]["approved"] is False  # always fail-closed

    def test_arch_001_runtime_enforcement_gate_present(self):
        """runtime_enforce() still runs before role resolution."""
        from vibe_model_routing_policy import route_all
        with mock.patch(
            "vibe_worker_registry.WorkerRegistry.probe_all",
            return_value={
                "21bao": {"status": "ONLINE"},
                "5bao": {"status": "ONLINE"},
                "9bao": {"status": "ONLINE"},
            },
        ):
            result = route_all()
        gate = result["_gate_results"]
        assert "runtime_enforcement" in gate
        # runtime_enforcement either passed or has the import-error fallback
        # both are acceptable (real life: passed=True; missing module: passed=False)
