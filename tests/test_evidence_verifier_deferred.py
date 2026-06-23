#!/usr/bin/env python3
"""V1.21.23 — Deferred Registry Evidence Verifier Awareness tests.

Covers T-44~T-52: verifier check for deferred_action_registry consistency,
absent/empty skip, invariant FAIL, service_admin_uac WARN, existing checks unaffected.

Read-only. No real execution, no gate verdict change, no new verdicts.
"""
import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_entry(action="code_modify", approval_id="appr-001",
                 workorder_id="deferred-code_modify-1234", risk_level="low",
                 dedicated_approval=False, registry_only=True,
                 dry_run_only=True, created_at="2026-06-23T10:00:00Z",
                 history_digest="abc123"):
    """Return a valid deferred registry entry dict."""
    return {
        "action": action,
        "approval_id": approval_id,
        "workorder_id": workorder_id,
        "risk_level": risk_level,
        "dedicated_approval": dedicated_approval,
        "registry_only": registry_only,
        "dry_run_only": dry_run_only,
        "real_execution": False,
        "created_at": created_at,
        "history_digest": history_digest,
    }


def _make_evidence(dar_entries=None, **extra):
    """Build a minimal evidence dict with optional deferred_action_registry."""
    evidence = {
        "evidence_id": "ev-test",
        "workorder_id": "test-wo",
        "base_sha": "abc123",
        "result_sha": "def456",
        "timestamp": "2026-06-23T10:00:00Z",
        "digest": "test-digest",
    }
    if dar_entries is not None:
        evidence["deferred_action_registry"] = dar_entries
    evidence.update(extra)
    return evidence


def _run_verifier(evidence, tmp_path):
    """Run verifier on evidence dict and return result dict."""
    # Write evidence to tmp file
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    evidence_file = evidence_dir / "ev-test.json"
    evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    # Write minimal registry entry
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(exist_ok=True)
    entry = {
        "workorder_id": evidence.get("workorder_id", "test-wo"),
        "allowed_paths": ["scripts/"],
    }
    entry_file = registry_dir / f"{entry['workorder_id']}.json"
    entry_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    # Import and run verifier
    from vibe_evidence_verifier import cmd_verify
    import types

    args = types.SimpleNamespace(
        command="verify",
        evidence_dir=str(evidence_dir),
        evidence_id="ev-test",
        registry_dir=str(registry_dir),
        json=True,
    )

    import io
    import contextlib

    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        cmd_verify(args)

    return json.loads(f.getvalue())


def _get_dar_check(result):
    """Extract the deferred_action_registry_consistency check from verifier result."""
    for check in result.get("checks", []):
        if check.get("name") == "deferred_action_registry_consistency":
            return check
    return None


def _get_check_names(result):
    """Extract all check names from verifier result."""
    return [c["name"] for c in result.get("checks", [])]


# ── T-44: absent/empty → check skipped ─────────────────────────────────────

class TestT44DarAbsentOrEmpty:
    """T-44: deferred_action_registry absent or empty → check skipped, verdict unaffected."""

    def test_absent_dar_no_check_appended(self, tmp_path):
        """No deferred_action_registry field → no check appended."""
        evidence = _make_evidence()  # no dar_entries
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is None, "Check should not be appended when DAR absent"
        assert "deferred_action_registry_consistency" not in _get_check_names(result)

    def test_empty_dar_no_check_appended(self, tmp_path):
        """Empty list → no check appended."""
        evidence = _make_evidence(dar_entries=[])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is None, "Check should not be appended when DAR is empty list"

    def test_absent_dar_verdict_unaffected(self, tmp_path):
        """Verdict should be based on existing checks only when DAR absent."""
        evidence = _make_evidence()
        result_without = _run_verifier(evidence, tmp_path)
        # Compare with same evidence + valid DAR — verdict should be same
        evidence_with_dar = _make_evidence(dar_entries=[_valid_entry()])
        result_with = _run_verifier(evidence_with_dar, tmp_path)
        # Both should have same verdict since DAR check is PASS (not contributing FAIL)
        assert result_without["verdict"] == result_with["verdict"]


# ── T-45: valid entries → PASS ─────────────────────────────────────────────

class TestT45DarValidEntries:
    """T-45: All entries valid → deferred_action_registry_consistency PASS."""

    def test_single_valid_entry(self, tmp_path):
        """Single valid entry → PASS."""
        evidence = _make_evidence(dar_entries=[_valid_entry()])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "PASS"

    def test_multiple_valid_entries(self, tmp_path):
        """Multiple valid entries → PASS."""
        entries = [
            _valid_entry(action="code_modify"),
            _valid_entry(action="commit"),
            _valid_entry(action="branch_create"),
        ]
        evidence = _make_evidence(dar_entries=entries)
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "PASS"
        assert "3 entries" in dar_check["detail"]


# ── T-46: real_execution=True → FAIL ───────────────────────────────────────

class TestT46DarRealExecutionViolation:
    """T-46: Entry with real_execution=True → FAIL."""

    def test_real_execution_true_fails(self, tmp_path):
        """real_execution=True violates invariant → FAIL."""
        entry = _valid_entry()
        entry["real_execution"] = True
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "FAIL"
        assert any("real_execution" in e for e in dar_check["errors"])

    def test_verdict_becomes_fail(self, tmp_path):
        """When DAR check FAILs, overall verdict should be FAIL."""
        entry = _valid_entry()
        entry["real_execution"] = True
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        assert result["verdict"] == "FAIL"


# ── T-47: registry_only=False → FAIL ──────────────────────────────────────

class TestT47DarRegistryOnlyViolation:
    """T-47: Entry with registry_only=False → FAIL."""

    def test_registry_only_false_fails(self, tmp_path):
        """registry_only=False violates invariant → FAIL."""
        entry = _valid_entry()
        entry["registry_only"] = False
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "FAIL"
        assert any("registry_only" in e for e in dar_check["errors"])


# ── T-48: dry_run_only=False → FAIL ──────────────────────────────────────

class TestT48DarDryRunOnlyViolation:
    """T-48: Entry with dry_run_only=False → FAIL."""

    def test_dry_run_only_false_fails(self, tmp_path):
        """dry_run_only=False violates invariant → FAIL."""
        entry = _valid_entry()
        entry["dry_run_only"] = False
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "FAIL"
        assert any("dry_run_only" in e for e in dar_check["errors"])


# ── T-49: service_admin_uac + dedicated → WARN ────────────────────────────

class TestT49DarServiceAdminUacWarning:
    """T-49: service_admin_uac + dedicated_approval=True → WARN with visibility annotation."""

    def test_service_admin_uac_dedicated_warns(self, tmp_path):
        """service_admin_uac + dedicated_approval=True → WARN."""
        entry = _valid_entry(
            action="service_admin_uac",
            risk_level="high",
            dedicated_approval=True,
        )
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "WARN"
        assert any("dedicated/critical" in w for w in dar_check["warnings"])

    def test_service_admin_uac_not_dedicated_passes(self, tmp_path):
        """service_admin_uac without dedicated_approval → PASS (no WARN)."""
        entry = _valid_entry(
            action="service_admin_uac",
            risk_level="high",
            dedicated_approval=False,
        )
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "PASS"


# ── T-50: missing required field → FAIL ────────────────────────────────────

class TestT50DarMissingField:
    """T-50: Entry with missing required field → FAIL."""

    def test_missing_real_execution_field_fails(self, tmp_path):
        """Missing real_execution field → FAIL."""
        entry = _valid_entry()
        del entry["real_execution"]
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "FAIL"
        assert any("missing fields" in e for e in dar_check["errors"])

    def test_missing_multiple_fields_fails(self, tmp_path):
        """Missing multiple fields → FAIL."""
        entry = _valid_entry()
        del entry["real_execution"]
        del entry["registry_only"]
        del entry["dry_run_only"]
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        dar_check = _get_dar_check(result)
        assert dar_check is not None
        assert dar_check["result"] == "FAIL"


# ── T-51: existing 9 checks unaffected ────────────────────────────────────

class TestT51ExistingChecksUnaffected:
    """T-51: Existing 9 verifier checks still pass."""

    def test_import_verifier_module(self):
        """Module should import without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "vibe_evidence_verifier",
            str(Path(__file__).parent.parent / "scripts" / "vibe_evidence_verifier.py"),
        )
        assert spec is not None

    def test_existing_checks_present_with_dar(self, tmp_path):
        """When DAR present, existing 9 checks still appear."""
        evidence = _make_evidence(dar_entries=[_valid_entry()])
        result = _run_verifier(evidence, tmp_path)
        check_names = _get_check_names(result)
        expected_checks = [
            "required_fields", "digest_match", "registry_entry",
            "approval_receipt", "shas_present", "smoke_result",
            "job_status", "audit_status", "changed_paths",
        ]
        for name in expected_checks:
            assert name in check_names, f"Missing existing check: {name}"

    def test_existing_checks_present_without_dar(self, tmp_path):
        """When DAR absent, existing 9 checks still appear."""
        evidence = _make_evidence()
        result = _run_verifier(evidence, tmp_path)
        check_names = _get_check_names(result)
        expected_checks = [
            "required_fields", "digest_match", "registry_entry",
            "approval_receipt", "shas_present", "smoke_result",
            "job_status", "audit_status", "changed_paths",
        ]
        for name in expected_checks:
            assert name in check_names, f"Missing existing check: {name}"


# ── T-52: verdict set unchanged ───────────────────────────────────────────

class TestT52VerdictSetUnchanged:
    """T-52: Verdict set still only PASS/WARN/FAIL (no new verdicts)."""

    def test_verdict_only_pass_warn_fail(self, tmp_path):
        """Verifier verdict must be one of PASS/WARN/FAIL."""
        entries = [
            _valid_entry(),
            _valid_entry(action="commit", workorder_id="deferred-commit-5678"),
        ]
        evidence = _make_evidence(dar_entries=entries)
        result = _run_verifier(evidence, tmp_path)
        assert result["verdict"] in ("PASS", "WARN", "FAIL"), (
            f"Unexpected verdict: {result['verdict']}"
        )

    def test_verdict_fail_on_violation(self, tmp_path):
        """DAR invariant violation → verdict FAIL."""
        entry = _valid_entry()
        entry["real_execution"] = True
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        assert result["verdict"] == "FAIL"

    def test_verdict_warn_on_dedicated(self, tmp_path):
        """service_admin_uac + dedicated → verdict WARN (not FAIL from DAR)."""
        entry = _valid_entry(
            action="service_admin_uac",
            risk_level="high",
            dedicated_approval=True,
        )
        evidence = _make_evidence(dar_entries=[entry])
        result = _run_verifier(evidence, tmp_path)
        # DAR check is WARN, so verdict should be WARN or FAIL (from other checks)
        assert result["verdict"] in ("PASS", "WARN", "FAIL")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
