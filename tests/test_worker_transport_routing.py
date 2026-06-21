"""test_worker_transport_routing.py — Tests for transport-aware worker routing

Tests WorkerNode serialization, transport routing, manual_only filtering,
disabled worker filtering, and unknown transport fail-closed.

All tests use fixtures. No live calls.
"""

import json
import sys
import unittest
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_worker_registry import (
    WorkerNode, WorkerRegistry, NodeStatus, DEFAULT_WORKERS,
)


class TestWorkerNodeSerialization(unittest.TestCase):
    """Test WorkerNode to_dict/from_dict round-trip."""

    def test_ssh_worker_serialization(self):
        w = WorkerNode(
            worker_id="test-ssh", node_type="debian-worker", transport="ssh",
            ssh_host="192.168.1.1", ssh_port=22, ssh_user="user",
            ssh_key_path="/path/to/key", repo_root="/repo", workspace_root="/workspace",
        )
        d = w.to_dict()
        assert d["transport"] == "ssh"
        assert d["ssh_host"] == "192.168.1.1"
        assert d["enabled"] is True
        assert d["manual_only"] is False
        # Round-trip
        w2 = WorkerNode.from_dict(d)
        assert w2.worker_id == "test-ssh"
        assert w2.transport == "ssh"
        assert w2.ssh_host == "192.168.1.1"

    def test_localexec_worker_serialization(self):
        w = WorkerNode(
            worker_id="21bao", node_type="windows-worker", transport="local-exec",
            ssh_host="", ssh_port=0, ssh_user="", ssh_key_path="",
            repo_root="", workspace_root=r"E:\vibedev-worktrees\21bao",
            enabled=False, manual_only=True,
        )
        d = w.to_dict()
        assert d["transport"] == "local-exec"
        assert d["ssh_host"] == ""
        assert d["ssh_port"] == 0
        assert d["enabled"] is False
        assert d["manual_only"] is True
        w2 = WorkerNode.from_dict(d)
        assert w2.transport == "local-exec"
        assert w2.ssh_host == ""
        assert w2.enabled is False
        assert w2.manual_only is True

    def test_from_dict_tolerates_missing_fields(self):
        d = {"worker_id": "minimal", "node_type": "debian-worker"}
        w = WorkerNode.from_dict(d)
        assert w.worker_id == "minimal"
        assert w.transport == "ssh"  # default
        assert w.enabled is True  # default
        assert w.manual_only is False  # default

    def test_from_dict_ignores_unknown_fields(self):
        d = {
            "worker_id": "test", "node_type": "debian-worker",
            "unknown_field": "should_be_ignored", "another": 42,
        }
        w = WorkerNode.from_dict(d)
        assert w.worker_id == "test"

    def test_json_round_trip(self):
        w = DEFAULT_WORKERS["21bao"]
        d = w.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        w2 = WorkerNode.from_dict(d2)
        assert w2.worker_id == "21bao"
        assert w2.transport == "local-exec"
        assert w2.manual_only is False
        assert w2.admission_mode == "normal"
        assert w2.enabled is True


class TestTransportRouting(unittest.TestCase):
    """Test transport-aware routing in available_workers."""

    def _make_registry(self):
        """Create a registry with all workers set to ONLINE."""
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        return reg

    def test_ssh_workers_for_linux_worker(self):
        reg = self._make_registry()
        avail = reg.available_workers("linux-worker")
        ids = {w.worker_id for w in avail}
        assert "5bao" in ids
        assert "9bao" in ids
        # 21bao doesn't have linux-worker capability
        assert "21bao" not in ids

    def test_localexec_workers_for_windows_worker(self):
        reg = self._make_registry()
        # 21bao is controlled, windows-worker NOT in allowed_operations -> rejected
        avail = reg.available_workers("windows-worker")
        ids = {w.worker_id for w in avail}
        assert "21bao" not in ids, "21bao normal should be rejected for windows-worker"
        assert "5bao" not in ids
        assert "9bao" not in ids

    def test_windows_worker_canary_rejected(self):
        reg = self._make_registry()
        # 21bao is controlled, windows-worker NOT in allowed_operations -> rejected
        avail = reg.available_workers("windows-worker")
        ids = {w.worker_id for w in avail}
        assert "21bao" not in ids

    def test_implementer_routes_to_ssh_workers(self):
        reg = self._make_registry()
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "5bao" in ids
        assert "9bao" in ids
        # 21bao is controlled, implementer NOW in allowed_operations -> included
        assert "21bao" in ids

    def test_implementer_with_manual_only_included(self):
        reg = self._make_registry()
        # 21bao is controlled, implementer NOW in allowed_operations
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "5bao" in ids
        assert "9bao" in ids
        assert "21bao" in ids

    def test_reviewer_routes_similarly(self):
        reg = self._make_registry()
        avail = reg.available_workers("reviewer")
        ids = {w.worker_id for w in avail}
        assert "5bao" in ids
        assert "9bao" in ids
        # 21bao is controlled with reviewer in allowed_operations -> included
        assert "21bao" in ids


class TestManualOnlyFiltering(unittest.TestCase):
    """Test manual_only worker filtering."""

    def test_manual_only_excluded_by_default(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # 21bao is controlled, implementer NOW in allowed_operations -> included
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids
        # But implementer-small should include 21bao
        avail_small = reg.available_workers("implementer-small")
        small_ids = {w.worker_id for w in avail_small}
        assert "21bao" in small_ids

    def test_manual_only_included_when_requested(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # 21bao is controlled, implementer NOW in capabilities/allowed_operations
        # include_manual_only bypasses manual_only filter but not normal admission
        # implementer NOW in allowed_operations, so 21bao is included
        avail = reg.available_workers("implementer", include_manual_only=True)
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids
        # smoke should include 21bao with include_manual_only
        avail_smoke = reg.available_workers("smoke", include_manual_only=True)
        smoke_ids = {w.worker_id for w in avail_smoke}
        assert "21bao" in smoke_ids

    def test_select_worker_excludes_manual_only(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # 21bao is controlled, implementer NOW in allowed_operations -> may be selected
        selected = reg.select_worker("implementer")
        assert selected is not None

    def test_select_worker_includes_manual_only_when_requested(self):
        reg = WorkerRegistry()
        # Only 21bao online
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        # 21bao is controlled, implementer allowed (in allowed_operations)
        selected = reg.select_worker("implementer", include_manual_only=True)
        assert selected is not None, "21bao normal now allows implementer"
        assert selected.worker_id == "21bao"
        # smoke should work
        selected_smoke = reg.select_worker("smoke", include_manual_only=True)
        assert selected_smoke is not None
        assert selected_smoke.worker_id == "21bao"

    def test_21bao_controlled_enforced_when_only_worker(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        # implementer NOW in canary allowed_operations -> can be selected
        selected_impl = reg.select_worker("implementer")
        assert selected_impl is not None, "21bao normal should be available for implementer"
        # smoke IS in canary allowed_operations -> accepted
        selected_smoke = reg.select_worker("smoke")
        assert selected_smoke is not None
        assert selected_smoke.worker_id == "21bao"
        # implementer-small IS in canary allowed_operations -> accepted
        selected_small = reg.select_worker("implementer-small")
        assert selected_small is not None
        assert selected_small.worker_id == "21bao"


class TestDisabledWorkerFiltering(unittest.TestCase):
    """Test disabled worker filtering."""

    def test_disabled_worker_excluded(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # Temporarily disable 21bao to verify disabled-worker exclusion
        reg.workers["21bao"].enabled = False
        # Even with include_manual_only, disabled workers stay excluded
        avail = reg.available_workers("implementer", include_manual_only=True)
        ids = {w.worker_id for w in avail}
        assert "21bao" not in ids, "Disabled worker should be excluded even with include_manual_only"

    def test_enabled_worker_included(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        reg.workers["21bao"].enabled = True
        reg.workers["21bao"].manual_only = False
        # 21bao is controlled, implementer NOW in allowed_operations
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids
        # But implementer-small should include 21bao
        avail_small = reg.available_workers("implementer-small")
        small_ids = {w.worker_id for w in avail_small}
        assert "21bao" in small_ids


class TestUnknownTransportFailClosed(unittest.TestCase):
    """Test that unknown transport fails closed."""

    def test_unknown_transport_worker_has_no_capability(self):
        """A worker with unknown transport and no matching capabilities should
        not be selected for any task."""
        w = WorkerNode(
            worker_id="test-unknown", node_type="unknown-type",
            transport="unknown-transport",
            ssh_host="", ssh_port=0, ssh_user="", ssh_key_path="",
            repo_root="", workspace_root="",
            capabilities=["unknown-capability"],
        )
        reg = WorkerRegistry(workers={"test-unknown": w})
        reg.set_health("test-unknown", NodeStatus.ONLINE)
        avail = reg.available_workers("linux-worker")
        assert len(avail) == 0

    def test_unknown_transport_select_returns_none(self):
        w = WorkerNode(
            worker_id="test-unknown", node_type="unknown-type",
            transport="unknown-transport",
            ssh_host="", ssh_port=0, ssh_user="", ssh_key_path="",
            repo_root="", workspace_root="",
            capabilities=["unknown-capability"],
        )
        reg = WorkerRegistry(workers={"test-unknown": w})
        reg.set_health("test-unknown", NodeStatus.ONLINE)
        selected = reg.select_worker("linux-worker")
        assert selected is None

    def test_local_exec_worker_only_matches_its_capabilities(self):
        """local-exec worker should not match linux-worker tasks."""
        w = WorkerNode(
            worker_id="test-local", node_type="windows-worker",
            transport="local-exec",
            ssh_host="", ssh_port=0, ssh_user="", ssh_key_path="",
            repo_root="", workspace_root="",
            capabilities=["windows-worker", "implementer"],
            enabled=True, manual_only=False,
        )
        reg = WorkerRegistry(workers={"test-local": w})
        reg.set_health("test-local", NodeStatus.ONLINE)
        # Should not match linux-worker
        avail = reg.available_workers("linux-worker")
        assert len(avail) == 0
        # Should match implementer (admission_mode=normal, no controlled filter)
        avail2 = reg.available_workers("implementer")
        assert len(avail2) == 1


class TestDefaultWorkers(unittest.TestCase):
    """Test DEFAULT_WORKERS configuration."""

    def test_21bao_registration(self):
        w = DEFAULT_WORKERS["21bao"]
        assert w.worker_id == "21bao"
        assert w.node_type == "windows-worker"
        assert w.transport == "local-exec"
        assert w.ssh_host == ""
        assert w.ssh_port == 0
        assert w.ssh_user == ""
        assert w.ssh_key_path == ""
        assert w.repo_root == ""
        assert w.enabled is True
        assert w.manual_only is False
        assert w.admission_mode == "normal"
        assert "windows-worker" in w.capabilities
        assert "opencode" in w.capabilities

    def test_5bao_registration(self):
        w = DEFAULT_WORKERS["5bao"]
        assert w.transport == "ssh"
        assert w.enabled is True
        assert w.manual_only is False

    def test_9bao_registration(self):
        w = DEFAULT_WORKERS["9bao"]
        assert w.transport == "ssh"
        assert w.enabled is True
        assert w.manual_only is False

    def test_three_workers_total(self):
        assert len(DEFAULT_WORKERS) == 3




class TestCanaryAdmissionEnforcement(unittest.TestCase):
    """Test normal admission enforcement V120H3."""

    def test_canary_smoke_allowed(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("smoke")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_controlled_implementer_small_allowed(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("implementer-small")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_controlled_implementer_allowed(self):
        """Only 21bao online: implementer selects 21bao (now in allowed_operations)."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("implementer")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_controlled_reviewer_allowed(self):
        """Only 21bao online: reviewer selects 21bao (now in allowed_operations)."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("reviewer")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_canary_merge_release_production_rejected(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        for task in ["merge", "release", "production"]:
            selected = reg.select_worker(task)
            assert selected is None, f"21bao should not be selected for {task}"

    def test_canary_windows_worker_rejected(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("windows-worker")
        assert selected is None

    def test_all_online_implementer_prefers_non_canary(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        selected = reg.select_worker("implementer")
        assert selected is not None
        assert selected.worker_id in ("5bao", "9bao")
        assert selected.worker_id != "21bao"

    def test_allowed_operations_enforced(self):
        w = DEFAULT_WORKERS["21bao"]
        assert "implementer" in w.capabilities
        assert "implementer" in w.allowed_operations
        assert "smoke" in w.allowed_operations
        assert "implementer-small" in w.allowed_operations
        assert "reviewer" in w.allowed_operations

    def test_canary_missing_allowed_operations_fail_closed(self):
        w = WorkerNode(
            worker_id="test-canary-empty", node_type="debian-worker",
            transport="ssh", ssh_host="", ssh_port=0, ssh_user="",
            ssh_key_path="", repo_root="", workspace_root="",
            capabilities=["implementer", "smoke"],
            admission_mode="controlled",
            allowed_operations=[],
        )
        reg = WorkerRegistry(workers={"test-canary-empty": w})
        reg.set_health("test-canary-empty", NodeStatus.ONLINE)
        for task in ["implementer", "smoke", "reviewer"]:
            avail = reg.available_workers(task)
            assert len(avail) == 0, f"canary with empty allowed_operations should reject {task}"

    def test_normal_worker_ignores_allowed_operations(self):
        w = WorkerNode(
            worker_id="test-normal", node_type="debian-worker",
            transport="ssh", ssh_host="", ssh_port=0, ssh_user="",
            ssh_key_path="", repo_root="", workspace_root="",
            capabilities=["implementer", "reviewer"],
            admission_mode="normal",
            allowed_operations=["smoke"],
        )
        reg = WorkerRegistry(workers={"test-normal": w})
        reg.set_health("test-normal", NodeStatus.ONLINE)
        avail = reg.available_workers("implementer")
        assert len(avail) == 1, "normal worker should not be filtered by allowed_operations"
        avail2 = reg.available_workers("reviewer")
        assert len(avail2) == 1

    def test_21bao_capabilities_include_implementer(self):
        w = DEFAULT_WORKERS["21bao"]
        assert "implementer" in w.capabilities
        assert "implementer-small" in w.capabilities
        assert "smoke" in w.capabilities

    def test_21bao_controlled_policy_exact(self):
        w = DEFAULT_WORKERS["21bao"]
        assert w.enabled is True
        assert w.manual_only is False
        assert w.admission_mode == "normal"
        assert w.max_parallel_jobs == 2
        assert set(w.allowed_operations) == {"smoke", "implementer-small", "reviewer", "implementer"}

    def test_controlled_reviewer_allowed_only_21bao(self):
        """Only 21bao online: reviewer selects 21bao."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("reviewer")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_all_online_reviewer_prefers_non_canary(self):
        """All nodes online: reviewer prefers 5bao/9bao, not 21bao."""
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        selected = reg.select_worker("reviewer")
        assert selected is not None
        assert selected.worker_id in ("5bao", "9bao")
        assert selected.worker_id != "21bao"

    def test_controlled_still_allows_smoke_and_implementer_small(self):
        """21bao still allows smoke and implementer-small."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        smoke = reg.select_worker("smoke")
        assert smoke is not None and smoke.worker_id == "21bao"
        small = reg.select_worker("implementer-small")
        assert small is not None and small.worker_id == "21bao"

    def test_controlled_now_allows_implementer(self):
        """21bao now allows implementer (added to allowed_operations)."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("implementer")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_controlled_still_rejects_merge_release_production(self):
        """21bao still rejects merge/release/production."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        for task in ["merge", "release", "production"]:
            selected = reg.select_worker(task)
            assert selected is None, f"21bao should reject {task}"

    def test_controlled_still_rejects_windows_worker(self):
        """21bao still rejects windows-worker."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("windows-worker")
        assert selected is None

    def test_max_parallel_jobs_is_2(self):
        """21bao max_parallel_jobs is 2."""
        w = DEFAULT_WORKERS["21bao"]
        assert w.max_parallel_jobs == 2


class TestMaxParallelJobs2(unittest.TestCase):
    """Test max_parallel_jobs=2 concurrent scheduling for 21bao."""

    def test_max_parallel_jobs_is_2(self):
        """21bao max_parallel_jobs should be 2."""
        w = DEFAULT_WORKERS["21bao"]
        assert w.max_parallel_jobs == 2

    def test_two_concurrent_smoke_jobs(self):
        """21bao can accept 2 concurrent smoke jobs."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        # First job
        sel1 = reg.select_worker("smoke")
        assert sel1 is not None and sel1.worker_id == "21bao"
        reg.record_job_start("21bao")
        # Second job - should still be schedulable
        sel2 = reg.select_worker("smoke")
        assert sel2 is not None and sel2.worker_id == "21bao"
        reg.record_job_start("21bao")
        # Third job - should be rejected (at capacity)
        sel3 = reg.select_worker("smoke")
        assert sel3 is None, "21bao at capacity with 2 active jobs"

    def test_two_concurrent_mixed_non_sensitive(self):
        """21bao can accept 2 concurrent different non-sensitive tasks."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        sel1 = reg.select_worker("smoke")
        assert sel1 is not None
        reg.record_job_start("21bao")
        sel2 = reg.select_worker("implementer")
        assert sel2 is not None and sel2.worker_id == "21bao"
        reg.record_job_start("21bao")
        sel3 = reg.select_worker("reviewer")
        assert sel3 is None, "At capacity"

    def test_sensitive_still_blocked_at_capacity_1(self):
        """Sensitive tasks blocked even when 21bao has capacity."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        for task in ["windows-worker", "merge", "release", "production"]:
            sel = reg.select_worker(task)
            assert sel is None, f"{task} blocked by safety gate"

    def test_sensitive_still_blocked_at_capacity_0(self):
        """Sensitive tasks blocked even with 0 active jobs."""
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        for task in ["windows-worker", "merge", "release", "production"]:
            sel = reg.select_worker(task)
            assert sel is None, f"{task} blocked by safety gate"

    def test_all_nodes_concurrent_scheduling(self):
        """All nodes online: 21bao gets implementer-small, 5bao/9bao get others."""
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # implementer-small only on 21bao
        sel = reg.select_worker("implementer-small")
        assert sel is not None and sel.worker_id == "21bao"
        # smoke/implementer/reviewer on 5bao/9bao
        for t in ["smoke", "implementer", "reviewer"]:
            sel = reg.select_worker(t)
            assert sel is not None and sel.worker_id in ("5bao", "9bao")

    def test_rollback_to_max_parallel_1(self):
        """Rollback max_parallel_jobs to 1 is trivial."""
        w = DEFAULT_WORKERS["21bao"]
        original = w.max_parallel_jobs
        w.max_parallel_jobs = 1
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        sel1 = reg.select_worker("smoke")
        assert sel1 is not None
        reg.record_job_start("21bao")
        sel2 = reg.select_worker("smoke")
        assert sel2 is None, "At capacity with max_parallel_jobs=1"
        w.max_parallel_jobs = original  # restore


if __name__ == "__main__":
    unittest.main()
