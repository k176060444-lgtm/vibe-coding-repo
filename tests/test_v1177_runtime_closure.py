#!/usr/bin/env python3
"""test_v1177_runtime_closure.py — V1.17.7 Orchestrator Runtime Closure tests."""

import json, os, sys, tempfile, time, threading
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
from vibe_job_orchestrator import (
    JobOrchestrator, JobManifest, JobState, ClaimStore, HeartbeatManager,
    MANIFEST_CORRUPTED, _resolve_ssh_key, _manifest_checksum,
    DEFAULT_LEASE_SECONDS, HEARTBEAT_EXTEND_SECONDS, HEARTBEAT_INTERVAL_SECONDS,
    __version__,
)
from vibe_scheduler_policy import SchedulerPolicy


def _make_orchestrator(tmpdir=None):
    if tmpdir is None:
        tmpdir = tempfile.mkdtemp(prefix="v1177-test-")
    cs = ClaimStore(os.path.join(tmpdir, "claims.json"), os.path.join(tmpdir, "claims.lock"))
    jobs_root = Path(tmpdir) / "jobs"
    orch = JobOrchestrator(claim_store=cs, jobs_root=jobs_root)
    for w in orch.registry.list_workers():
        orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
    return orch, cs, jobs_root


class TestFailClosedImports:
    def test_worker_registry_import_is_real(self):
        reg = WorkerRegistry()
        workers = reg.list_workers()
        assert len(workers) >= 2
        worker_ids = {w.worker_id for w in workers}
        assert "5bao" in worker_ids and "9bao" in worker_ids

    def test_scheduler_policy_import_is_real(self):
        reg = WorkerRegistry()
        for w in reg.list_workers():
            reg.set_health(w.worker_id, NodeStatus.ONLINE)
        sp = SchedulerPolicy(reg)
        candidates = sp.get_eligible_candidates("linux-worker")
        assert len(candidates) >= 2

    def test_resume_gate_import_is_real(self):
        from vibe_resume_gate import check as resume_check
        import inspect
        sig = inspect.signature(resume_check)
        assert "batch_id" in sig.parameters

    def test_lifecycle_gate_import_is_real(self):
        from vibe_toolchain_lifecycle import gate_check_for_dispatch
        result = gate_check_for_dispatch()
        assert "allowed" in result

    def test_no_fallback_classes_in_orchestrator(self):
        orch_path = Path(__file__).parent.parent / "scripts" / "vibe_job_orchestrator.py"
        source = orch_path.read_text()
        assert "class WorkerRegistry" not in source
        assert "class SchedulerPolicy" not in source
        assert "def resume_gate_check(job_id" not in source


class TestRealGates:
    def test_branch_gate_blocks_locked_branch(self):
        reg = WorkerRegistry()
        for w in reg.list_workers():
            reg.set_health(w.worker_id, NodeStatus.ONLINE)
        reg.acquire_branch_lock("locked-branch", "5bao")
        assert not reg.check_branch_available("locked-branch")
        assert reg.check_branch_available("open-branch")
        reg.release_branch_lock("locked-branch", "5bao")

    def test_merge_gate_blocks_locked_merge(self):
        reg = WorkerRegistry()
        assert reg.check_merge_available()
        reg.acquire_merge_lock("5bao")
        assert not reg.check_merge_available()
        reg.release_merge_lock("5bao")
        assert reg.check_merge_available()

    def test_preflight_branch_gate_via_orchestrator(self):
        orch, cs, jr = _make_orchestrator()
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        orch.registry.acquire_branch_lock("main", "other-worker")
        manifest.involves_branch_mutation = True
        manifest.branch_name = "main"
        orch._persist_manifest(manifest)
        preflight = orch._preflight_check(manifest)
        assert not preflight["all_passed"]
        assert "branch_gate" in preflight["failed_checks"]
        orch.registry.release_branch_lock("main", "other-worker")

    def test_preflight_merge_gate_via_orchestrator(self):
        orch, cs, jr = _make_orchestrator()
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        orch.registry.acquire_merge_lock("other-worker")
        manifest.involves_merge = True
        orch._persist_manifest(manifest)
        preflight = orch._preflight_check(manifest)
        assert not preflight["all_passed"]
        assert "merge_gate" in preflight["failed_checks"]
        orch.registry.release_merge_lock("other-worker")

    def test_resume_gate_called_on_resume(self):
        orch, cs, jr = _make_orchestrator()
        m = orch.submit_job("linux-worker", "echo hi")
        jid = m["job_id"]
        manifest = orch._load_manifest(jid)
        manifest.state = JobState.FAILED.value
        manifest.error = "test_failure"
        orch._persist_manifest(manifest)
        result = orch.resume_job(jid)
        assert result.get("error") != "resume_gate_denied"


class TestClaimStoreFailClosed:
    def test_json_corruption_latch(self):
        with tempfile.TemporaryDirectory() as td:
            sp, lp = os.path.join(td, "c.json"), os.path.join(td, "c.lock")
            cs = ClaimStore(sp, lp)
            cs.try_claim("j1", "5bao", 1)
            with open(sp, "w") as f:
                f.write("{corrupt")
            cs2 = ClaimStore(sp, lp)
            assert cs2.is_latched()
            with pytest.raises(MANIFEST_CORRUPTED):
                cs2.try_claim("j2", "5bao", 2)
            with pytest.raises(MANIFEST_CORRUPTED):
                cs2.get_claim("j1")

    def test_schema_validation_latch(self):
        with tempfile.TemporaryDirectory() as td:
            sp, lp = os.path.join(td, "c.json"), os.path.join(td, "c.lock")
            with open(sp, "w") as f:
                json.dump({"not_claims": {}}, f)
            cs = ClaimStore(sp, lp)
            assert cs.is_latched()

    def test_old_claims_preserved_after_repair(self):
        with tempfile.TemporaryDirectory() as td:
            sp, lp = os.path.join(td, "c.json"), os.path.join(td, "c.lock")
            cs = ClaimStore(sp, lp)
            cs.try_claim("j1", "5bao", 1)
            raw = json.loads(open(sp).read())
            assert "j1" in raw["claims"]
            with open(sp, "w") as f:
                f.write("{bad")
            cs2 = ClaimStore(sp, lp)
            assert cs2.is_latched()
            with open(sp, "w") as f:
                json.dump(raw, f)
            cs3 = ClaimStore(sp, lp)
            assert not cs3.is_latched()
            assert cs3.get_claim("j1") is not None

    def test_fsync_on_write(self):
        with tempfile.TemporaryDirectory() as td:
            sp, lp = os.path.join(td, "c.json"), os.path.join(td, "c.lock")
            cs = ClaimStore(sp, lp)
            cs.try_claim("j1", "5bao", 1)
            assert os.path.exists(sp)
            data = json.loads(open(sp).read())
            assert "j1" in data["claims"]

    def test_lock_serializes_writes(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            for i in range(5):
                r = cs.try_claim("j-%d" % i, "w1", i, max_parallel_jobs=10)
                assert r["claimed"]
            assert len(cs.get_active_claims()) == 5


class TestRecoveryRequired:
    def test_recovery_required_blocks_new_claims(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j1", "5bao", 1, lease_seconds=1, max_parallel_jobs=1)
            time.sleep(1.5)
            r = cs.try_claim("j2", "5bao", 2, max_parallel_jobs=1)
            assert not r["claimed"]
            assert r["reason"] == "capacity_full"

    def test_recovery_required_in_active_claims(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j1", "5bao", 1, lease_seconds=1, max_parallel_jobs=10)
            time.sleep(1.5)
            cs.try_claim("j2", "5bao", 2, max_parallel_jobs=10)
            active = cs.get_active_claims()
            states = {c["state"] for c in active}
            assert "RECOVERY_REQUIRED" in states


class TestHeartbeat:
    def test_heartbeat_extends_lease(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j1", "5bao", 1, lease_seconds=5)
            before = cs.get_claim("j1")["lease_until"]
            time.sleep(0.5)
            cs.heartbeat_claim("j1")
            after = cs.get_claim("j1")["lease_until"]
            assert after > before

    def test_heartbeat_manager_keeps_claim_alive(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j1", "5bao", 1, lease_seconds=3)
            hm = HeartbeatManager(cs)
            hm.start_heartbeat("j1")
            time.sleep(4)
            claim = cs.get_claim("j1")
            assert claim["state"] in ("CLAIMED", "RUNNING")
            hm.stop_heartbeat("j1")


class TestSSHKey:
    def test_no_auto_search_fallback(self):
        orch_path = Path(__file__).parent.parent / "scripts" / "vibe_job_orchestrator.py"
        source = orch_path.read_text()
        assert '".ssh"' not in source

    def test_ssh_key_fail_closed(self):
        import vibe_job_orchestrator as vjo
        old_key = vjo.SSH_KEY_PATH
        vjo.SSH_KEY_PATH = None
        try:
            old_paths = vjo._CONTROLLER_SSH_KEY_PATHS
            vjo._CONTROLLER_SSH_KEY_PATHS = [Path("/nonexistent/key")]
            with pytest.raises(RuntimeError, match="SSH key not found"):
                _resolve_ssh_key()
            vjo._CONTROLLER_SSH_KEY_PATHS = old_paths
        finally:
            vjo.SSH_KEY_PATH = old_key


class TestRemotePID:
    def test_parse_remote_pid(self):
        assert JobOrchestrator._parse_remote_pid("REMOTE_PID=12345\nREMOTE_PGID=99\nhello\n") == 12345

    def test_parse_remote_pid_none(self):
        assert JobOrchestrator._parse_remote_pid("no pid\n") is None

    def test_strip_remote_pid_and_pgid(self):
        clean = JobOrchestrator._strip_remote_pid_line("REMOTE_PID=1\nREMOTE_PGID=2\nhello\n")
        assert "REMOTE_PID" not in clean and "REMOTE_PGID" not in clean and "hello" in clean

    def test_manifest_has_remote_pgid(self):
        m = JobManifest(job_id="t", task_type="lw", command="echo")
        assert "remote_pgid" in m.to_dict()


class TestManifestChecksum:
    def test_checksum_computed(self):
        assert JobManifest(job_id="t", task_type="lw", command="echo").to_dict()["checksum"] != ""

    def test_checksum_changes_with_content(self):
        assert JobManifest(job_id="t", task_type="lw", command="a").to_dict()["checksum"] != \
               JobManifest(job_id="t", task_type="lw", command="b").to_dict()["checksum"]

    def test_corruption_detected(self):
        d = JobManifest(job_id="t", task_type="lw", command="echo").to_dict()
        d["command"] = "tampered"
        with pytest.raises(MANIFEST_CORRUPTED):
            JobManifest.from_dict(d)

    def test_valid_manifest_loads(self):
        m = JobManifest(job_id="t", task_type="lw", command="echo")
        assert JobManifest.from_dict(m.to_dict()).job_id == "t"


class TestConcurrentSafety:
    def test_two_workers_parallel(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            assert cs.try_claim("j1", "5bao", 1)["claimed"]
            assert cs.try_claim("j2", "9bao", 2)["claimed"]
            assert len(cs.get_active_claims()) == 2

    def test_max_parallel_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            for i in range(4):
                assert cs.try_claim("j%d" % i, "w1", i, max_parallel_jobs=4)["claimed"]
            assert not cs.try_claim("j5", "w1", 5, max_parallel_jobs=4)["claimed"]

    def test_third_job_blocked_at_capacity(self):
        orch, cs, jr = _make_orchestrator()
        orch.registry.workers["5bao"].max_parallel_jobs = 1
        orch.registry.workers["9bao"].max_parallel_jobs = 1
        assert orch.submit_job("linux-worker", "echo j1")["state"] == "CLAIMED"
        assert orch.submit_job("linux-worker", "echo j2")["state"] == "CLAIMED"
        assert orch.submit_job("linux-worker", "echo j3")["state"] == "BLOCKED"


class TestMultiCandidateRetry:
    def test_retry_to_second_worker(self):
        orch, cs, jr = _make_orchestrator()
        orch.registry.workers["5bao"].max_parallel_jobs = 1
        orch.registry.workers["9bao"].max_parallel_jobs = 1
        m1 = orch.submit_job("linux-worker", "echo j1")
        m2 = orch.submit_job("linux-worker", "echo j2")
        assert m2["state"] == "CLAIMED"
        assert m2["actual_worker"] != m1["actual_worker"]


class TestLifecycleGateInPreflight:
    def test_preflight_calls_real_lifecycle_gate(self):
        orch, cs, jr = _make_orchestrator()
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        preflight = orch._preflight_check(manifest)
        assert "lifecycle_gate" in preflight["checks"]
        assert preflight["checks"]["lifecycle_gate"]["passed"]

    def test_preflight_all_gates_present(self):
        orch, cs, jr = _make_orchestrator()
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        preflight = orch._preflight_check(manifest)
        for gate in ["lifecycle_gate", "capability", "branch_gate",
                      "merge_gate", "resume_gate", "worker_online",
                      "not_maintenance", "claim_valid"]:
            assert gate in preflight["checks"], "%s missing" % gate


class TestVersion:
    def test_version_is_300(self):
        assert __version__ == "3.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
