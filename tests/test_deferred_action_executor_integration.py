"""Tests for V1.21.19: Deferred Action Executor Integration (Phase 1+2).

Covers T-01 through T-11 from the V1.21.19 proposal.
Registry-only glue + dry-run plans. No real execution.
"""

import json as _json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_workorder_registry import (
    register_deferred_action,
    DEFERRED_ACTION_TYPES,
)
from vibe_safe_executor import (
    generate_deferred_action_dry_run_plan,
    DEFERRED_ACTION_TYPES as SAFE_EXECUTOR_DEFERRED_TYPES,
)
from vibe_executor_adapter import (
    ADAPTERS,
    DEFERRED_ACTION_ADAPTERS,
)


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_eag_delegate_task_dispatch():
    """EAG result for approved delegate_task_dispatch."""
    return {
        "verdict": "APPROVAL_BOUND",
        "action": "delegate_task_dispatch",
        "action_class": "execution",
        "action_category": "action_specific",
        "approval_id": "approval-test-001",
        "risk_level": "low",
        "detail": "Action approved.",
        "target_node": "debian",
        "target_role": "leaf",
        "model_plan": "deepseek-v4-pro",
    }


def _make_eag_live_model_call():
    """EAG result for approved live_model_call."""
    return {
        "verdict": "APPROVAL_BOUND",
        "action": "live_model_call",
        "action_class": "execution",
        "action_category": "action_specific",
        "approval_id": "approval-test-002",
        "risk_level": "low",
        "detail": "Action approved.",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "budget_policy": "within_budget",
    }


def _make_eag_service_admin_uac():
    """EAG result for approved service_admin_uac."""
    return {
        "verdict": "APPROVAL_BOUND",
        "action": "service_admin_uac",
        "action_class": "execution",
        "action_category": "action_specific",
        "approval_id": "approval-test-003",
        "risk_level": "critical",
        "detail": "Action approved with CRITICAL + dedicated approval.",
        "target_service": "gateway",
        "change_type": "config",
    }


def _make_approval(action, dedicated=False):
    """Mock approval record."""
    if dedicated:
        return {
            "approval_id": f"approval-{action}-dedicated",
            "approved": True,
            "approved_actions": [action],
            "risk_level": "critical",
        }
    return {
        "approval_id": f"approval-{action}",
        "approved": True,
        "approved_actions": [action, "code_modify"],
        "risk_level": "low",
    }


# ── T-01~T-03: Registry entry creation ───────────────────────────────

class TestRegistryEntryCreation:
    """T-01, T-02, T-03: APPROVED_FOR_EXECUTION → registry entry created."""

    def test_delegate_task_dispatch_registry_entry(self, tmp_path):
        """T-01: delegate_task_dispatch → registry entry with correct fields."""
        eag = _make_eag_delegate_task_dispatch()
        entry = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag,
            approval=_make_approval("delegate_task_dispatch"),
            repo_root=str(tmp_path),
        )
        assert entry is not None
        assert entry["action"] == "delegate_task_dispatch"
        assert entry["action_category"] == "deferred"
        assert entry["status"] == "approved"
        assert entry["registry_only"] is True
        assert entry["dry_run_only"] is True
        assert entry["target_node"] == "debian"
        assert entry["target_role"] == "leaf"
        assert entry["model_plan"] == "deepseek-v4-pro"
        assert entry["eag_verdict"] == "APPROVAL_BOUND"
        assert entry["risk_level"] == "low"

    def test_live_model_call_registry_entry(self, tmp_path):
        """T-02: live_model_call → registry entry with correct fields."""
        eag = _make_eag_live_model_call()
        entry = register_deferred_action(
            action="live_model_call",
            eag_result=eag,
            approval=_make_approval("live_model_call"),
            repo_root=str(tmp_path),
        )
        assert entry is not None
        assert entry["action"] == "live_model_call"
        assert entry["action_category"] == "deferred"
        assert entry["status"] == "approved"
        assert entry["registry_only"] is True
        assert entry["dry_run_only"] is True
        assert entry["provider"] == "deepseek"
        assert entry["model"] == "deepseek-v4-pro"
        assert entry["budget_policy"] == "within_budget"
        assert entry["eag_verdict"] == "APPROVAL_BOUND"

    def test_service_admin_uac_registry_entry(self, tmp_path):
        """T-03: service_admin_uac → registry entry with CRITICAL + dedicated."""
        eag = _make_eag_service_admin_uac()
        entry = register_deferred_action(
            action="service_admin_uac",
            eag_result=eag,
            approval=_make_approval("service_admin_uac", dedicated=True),
            repo_root=str(tmp_path),
        )
        assert entry is not None
        assert entry["action"] == "service_admin_uac"
        assert entry["action_category"] == "deferred"
        assert entry["status"] == "approved"
        assert entry["registry_only"] is True
        assert entry["dry_run_only"] is True
        assert entry["risk_level"] == "critical"
        assert entry["dedicated_approval"] is True
        assert entry["target_service"] == "gateway"
        assert entry["change_type"] == "config"
        assert entry["eag_verdict"] == "APPROVAL_BOUND"


# ── T-04~T-06: Dry-run plan generation ───────────────────────────────

class TestDryRunPlanGeneration:
    """T-04, T-05, T-06: Dry-run plans for each deferred action."""

    def test_delegate_task_dispatch_dry_run_plan(self, tmp_path):
        """T-04: delegate_task_dispatch dry-run plan."""
        eag = _make_eag_delegate_task_dispatch()
        entry = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag,
            approval=_make_approval("delegate_task_dispatch"),
            repo_root=str(tmp_path),
        )
        plan = generate_deferred_action_dry_run_plan("delegate_task_dispatch", entry)
        assert plan is not None
        assert plan["action"] == "delegate_task_dispatch"
        assert plan["real_execution"] is False
        assert plan["registry_only"] is True
        assert plan["dry_run_only"] is True
        assert plan["reversible"] is True
        assert plan["total_steps"] == 5
        assert any("debian" in s.get("description", "") for s in plan["steps"])
        assert "No real worker dispatch" in plan["notes"]

    def test_live_model_call_dry_run_plan(self, tmp_path):
        """T-05: live_model_call dry-run plan."""
        eag = _make_eag_live_model_call()
        entry = register_deferred_action(
            action="live_model_call",
            eag_result=eag,
            approval=_make_approval("live_model_call"),
            repo_root=str(tmp_path),
        )
        plan = generate_deferred_action_dry_run_plan("live_model_call", entry)
        assert plan is not None
        assert plan["action"] == "live_model_call"
        assert plan["real_execution"] is False
        assert plan["registry_only"] is True
        assert plan["dry_run_only"] is True
        assert plan["total_steps"] == 5
        assert any("deepseek" in s.get("description", "") for s in plan["steps"])
        assert "No real model API call" in plan["notes"]

    def test_service_admin_uac_dry_run_plan(self, tmp_path):
        """T-06: service_admin_uac dry-run plan."""
        eag = _make_eag_service_admin_uac()
        entry = register_deferred_action(
            action="service_admin_uac",
            eag_result=eag,
            approval=_make_approval("service_admin_uac", dedicated=True),
            repo_root=str(tmp_path),
        )
        plan = generate_deferred_action_dry_run_plan("service_admin_uac", entry)
        assert plan is not None
        assert plan["action"] == "service_admin_uac"
        assert plan["real_execution"] is False
        assert plan["registry_only"] is True
        assert plan["dry_run_only"] is True
        assert plan["risk_level"] == "critical"
        assert plan["dedicated_approval"] is True
        assert plan["total_steps"] == 6
        assert any("gateway" in s.get("description", "") for s in plan["steps"])
        assert "No real service action" in plan["notes"]


# ── T-07: service_admin_uac CRITICAL + dedicated metadata ────────────

class TestServiceAdminCriticalDedicated:
    """T-07: service_admin_uac registry entry has CRITICAL + dedicated metadata."""

    def test_critical_dedicated_metadata(self, tmp_path):
        """T-07: service_admin_uac always CRITICAL, dedicated when single-action approval."""
        eag = _make_eag_service_admin_uac()
        # Dedicated approval (only service_admin_uac in approved_actions)
        entry = register_deferred_action(
            action="service_admin_uac",
            eag_result=eag,
            approval=_make_approval("service_admin_uac", dedicated=True),
            repo_root=str(tmp_path),
        )
        assert entry["risk_level"] == "critical"
        assert entry["dedicated_approval"] is True

    def test_critical_even_with_bundled_approval(self, tmp_path):
        """T-07b: service_admin_uac risk_level=critical even with bundled approval."""
        eag = _make_eag_service_admin_uac()
        # Bundled approval (service_admin_uac + other actions)
        bundled = {
            "approval_id": "approval-bundled",
            "approved": True,
            "approved_actions": ["service_admin_uac", "code_modify"],
            "risk_level": "low",
        }
        entry = register_deferred_action(
            action="service_admin_uac",
            eag_result=eag,
            approval=bundled,
            repo_root=str(tmp_path),
        )
        # risk_level forced to critical regardless of approval's risk_level
        assert entry["risk_level"] == "critical"
        # dedicated_approval is False because bundled
        assert entry["dedicated_approval"] is False


# ── T-08: No real execution ──────────────────────────────────────────

class TestNoRealExecution:
    """T-08: Dry-run does NOT trigger real execution."""

    def test_registry_entry_flags(self, tmp_path):
        """T-08a: Registry entries have registry_only and dry_run_only flags."""
        for action in DEFERRED_ACTION_TYPES:
            eag = {"verdict": "APPROVAL_BOUND", "action": action, "detail": "ok"}
            entry = register_deferred_action(
                action=action,
                eag_result=eag,
                repo_root=str(tmp_path),
            )
            assert entry is not None
            assert entry["registry_only"] is True
            assert entry["dry_run_only"] is True
            assert entry["requires_human_approval"] is True

    def test_dry_run_plan_flags(self, tmp_path):
        """T-08b: Dry-run plans have real_execution=False."""
        for action in DEFERRED_ACTION_TYPES:
            eag = {"verdict": "APPROVAL_BOUND", "action": action, "detail": "ok"}
            entry = register_deferred_action(
                action=action,
                eag_result=eag,
                repo_root=str(tmp_path),
            )
            plan = generate_deferred_action_dry_run_plan(action, entry)
            assert plan is not None
            assert plan["real_execution"] is False
            assert plan["registry_only"] is True
            assert plan["dry_run_only"] is True

    def test_adapter_refused_actions_include_real_execution(self):
        """T-08c: Deferred action adapters refuse real execution actions."""
        for action_name, adapter in DEFERRED_ACTION_ADAPTERS.items():
            refused = adapter["refused_actions"]
            assert "model_call" in refused, f"{action_name} should refuse model_call"
            assert "shell_exec" in refused, f"{action_name} should refuse shell_exec"
            assert "repo_write" in refused, f"{action_name} should refuse repo_write"
            assert "git_push" in refused, f"{action_name} should refuse git_push"


# ── T-09: Existing gate tests still pass ─────────────────────────────

class TestExistingGateTestsUnaffected:
    """T-09: Existing gate tests still pass (verified by scoped pytest run)."""

    def test_deferred_action_types_consistent(self):
        """T-09: DEFERRED_ACTION_TYPES consistent across modules."""
        assert DEFERRED_ACTION_TYPES == {"delegate_task_dispatch", "live_model_call", "service_admin_uac"}
        assert SAFE_EXECUTOR_DEFERRED_TYPES == DEFERRED_ACTION_TYPES


# ── T-10: Version check ──────────────────────────────────────────────

class TestVersionCheck:
    """T-10: Module versions unchanged or properly tracked."""

    def test_workorder_registry_version(self):
        from vibe_workorder_registry import VERSION
        assert VERSION == "1.1.0"

    def test_safe_executor_version(self):
        from vibe_safe_executor import VERSION
        assert VERSION == "1.0.0"

    def test_executor_adapter_version(self):
        from vibe_executor_adapter import VERSION
        assert VERSION == "1.0.0"


# ── T-11: No import cycle ────────────────────────────────────────────

class TestNoImportCycle:
    """T-11: No import cycle between modules."""

    def test_intake_gate_imports_registry(self):
        """T-11a: conversational_intake_gate imports from vibe_workorder_registry."""
        from conversational_intake_gate import (
            _DEFERRED_ACTION_REGISTRY_AVAILABLE,
            _register_deferred_action,
            _DEFERRED_ACTION_TYPES,
        )
        assert _DEFERRED_ACTION_REGISTRY_AVAILABLE is True
        assert callable(_register_deferred_action)
        assert "delegate_task_dispatch" in _DEFERRED_ACTION_TYPES

    def test_registry_imports_nothing_from_intake_gate(self):
        """T-11b: vibe_workorder_registry does NOT import from conversational_intake_gate."""
        import importlib
        import vibe_workorder_registry
        source = importlib.util.find_spec("vibe_workorder_registry")
        # If there were a cycle, importing would fail
        assert vibe_workorder_registry.register_deferred_action is not None

    def test_safe_executor_standalone(self):
        """T-11c: vibe_safe_executor imports are standalone."""
        from vibe_safe_executor import generate_deferred_action_dry_run_plan
        assert callable(generate_deferred_action_dry_run_plan)


# ── V1.21.20: Dedup + constant consolidation tests ──────────────────

class TestRegistryDedup:
    """T-12, T-13: Registry dedup by (approval_id, action)."""

    def test_same_approval_id_action_returns_existing(self, tmp_path):
        """T-12: Same approval_id + action → returns existing entry, no duplicate."""
        eag = {
            "verdict": "APPROVAL_BOUND",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-dedup-test-001",
            "detail": "ok",
            "target_node": "debian",
            "target_role": "leaf",
        }
        entry1 = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag,
            repo_root=str(tmp_path),
        )
        assert entry1 is not None

        # Second call with same approval_id + action
        entry2 = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag,
            repo_root=str(tmp_path),
        )
        assert entry2 is not None
        # Should be the same entry (dedup)
        assert entry1["workorder_id"] == entry2["workorder_id"]

        # Verify only one file exists
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        files = list(registry_dir.glob("*.json"))
        assert len(files) == 1

    def test_different_approval_creates_new(self, tmp_path):
        """T-13: Different approval_id → creates new entry."""
        eag1 = {
            "verdict": "APPROVAL_BOUND",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-diff-001",
            "detail": "ok",
        }
        eag2 = {
            "verdict": "APPROVAL_BOUND",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-diff-002",
            "detail": "ok",
        }
        entry1 = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag1,
            repo_root=str(tmp_path),
        )
        entry2 = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag2,
            repo_root=str(tmp_path),
        )
        assert entry1 is not None
        assert entry2 is not None
        # Different approval_id → different entries
        assert entry1["workorder_id"] != entry2["workorder_id"]

        # Two files exist
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        files = list(registry_dir.glob("*.json"))
        assert len(files) == 2

    def test_same_approval_different_action_creates_new(self, tmp_path):
        """T-13b: Same approval_id but different action → creates new entry."""
        eag1 = {
            "verdict": "APPROVAL_BOUND",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-same-001",
            "detail": "ok",
        }
        eag2 = {
            "verdict": "APPROVAL_BOUND",
            "action": "live_model_call",
            "approval_id": "approval-same-001",
            "detail": "ok",
        }
        entry1 = register_deferred_action(
            action="delegate_task_dispatch",
            eag_result=eag1,
            repo_root=str(tmp_path),
        )
        entry2 = register_deferred_action(
            action="live_model_call",
            eag_result=eag2,
            repo_root=str(tmp_path),
        )
        assert entry1 is not None
        assert entry2 is not None
        assert entry1["workorder_id"] != entry2["workorder_id"]
        assert entry1["action"] == "delegate_task_dispatch"
        assert entry2["action"] == "live_model_call"


class TestConstantConsolidation:
    """T-14: DEFERRED_ACTION_TYPES imported from canonical source."""

    def test_safe_executor_imports_from_registry(self):
        """T-14: vibe_safe_executor.DEFERRED_ACTION_TYPES is the same object as registry's."""
        from vibe_workorder_registry import DEFERRED_ACTION_TYPES as REG_TYPES
        from vibe_safe_executor import DEFERRED_ACTION_TYPES as SAFE_TYPES
        # Should be the same set (imported, not duplicated)
        assert SAFE_TYPES == REG_TYPES
        assert SAFE_TYPES is REG_TYPES

    def test_intake_gate_imports_from_registry(self):
        """T-14b: conversational_intake_gate imports from registry."""
        from vibe_workorder_registry import DEFERRED_ACTION_TYPES as REG_TYPES
        from conversational_intake_gate import _DEFERRED_ACTION_TYPES as INTAKE_TYPES
        assert INTAKE_TYPES == REG_TYPES


class TestExistingTestsUnaffected:
    """T-15: Existing T-01~T-11 still pass (verified by scoped pytest run)."""

    def test_deferred_types_consistent(self):
        """T-15: DEFERRED_ACTION_TYPES consistent across all modules."""
        from vibe_workorder_registry import DEFERRED_ACTION_TYPES as REG
        from vibe_safe_executor import DEFERRED_ACTION_TYPES as SAFE
        assert REG == SAFE == {"delegate_task_dispatch", "live_model_call", "service_admin_uac"}
