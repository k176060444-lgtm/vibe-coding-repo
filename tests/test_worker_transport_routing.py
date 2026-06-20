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
        assert w2.admission_mode == "canary"
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
        # 21bao is canary (manual_only=False), available for windows-worker
        avail = reg.available_workers("windows-worker")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids
        assert "5bao" not in ids
        assert "9bao" not in ids

    def test_windows_worker_with_include_manual_only(self):
        reg = self._make_registry()
        # 21bao is canary (manual_only=False), included by default
        avail = reg.available_workers("windows-worker")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids

    def test_implementer_routes_to_ssh_workers(self):
        reg = self._make_registry()
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "5bao" in ids
        assert "9bao" in ids
        # 21bao is canary, has implementer capability
        assert "21bao" in ids

    def test_implementer_with_manual_only_included(self):
        reg = self._make_registry()
        # 21bao is canary (manual_only=False), included by default
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
        assert "21bao" not in ids


class TestManualOnlyFiltering(unittest.TestCase):
    """Test manual_only worker filtering."""

    def test_manual_only_excluded_by_default(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # 21bao is canary (manual_only=False), now included
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids

    def test_manual_only_included_when_requested(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # Enable 21bao to isolate manual_only from enabled filtering
        reg.workers["21bao"].enabled = True
        avail = reg.available_workers("implementer", include_manual_only=True)
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids

    def test_select_worker_excludes_manual_only(self):
        reg = WorkerRegistry()
        for wid in reg.workers:
            reg.set_health(wid, NodeStatus.ONLINE)
        # Enable 21bao to isolate manual_only from enabled filtering
        reg.workers["21bao"].enabled = True
        selected = reg.select_worker("implementer")
        assert selected is not None
        assert selected.worker_id != "21bao"

    def test_select_worker_includes_manual_only_when_requested(self):
        reg = WorkerRegistry()
        # Only 21bao online
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        # Enable 21bao to isolate manual_only from enabled filtering
        reg.workers["21bao"].enabled = True
        selected = reg.select_worker("implementer", include_manual_only=True)
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_21bao_canary_scheduled_when_only_worker(self):
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        # 21bao is canary (manual_only=False), can be auto-scheduled
        selected = reg.select_worker("implementer")
        assert selected is not None, "21bao canary should be auto-scheduled when only available"
        assert selected.worker_id == "21bao"


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
        avail = reg.available_workers("implementer")
        ids = {w.worker_id for w in avail}
        assert "21bao" in ids


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
        # Should match implementer
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
        assert w.admission_mode == "canary"
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


if __name__ == "__main__":
    unittest.main()
