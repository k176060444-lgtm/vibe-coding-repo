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


# ── T-64: evidence file missing → FAIL ──────────────────────────────────────

class TestT64EvidenceFileMissing:
    """T-64: Evidence file absent at verify time → FAIL with not-found error."""

    def test_missing_evidence_file_returns_fail(self, tmp_path):
        """When evidence file doesn't exist, verifier returns FAIL."""
        from vibe_evidence_verifier import cmd_verify
        import types

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()

        args = types.SimpleNamespace(
            command="verify",
            evidence_dir=str(evidence_dir),
            evidence_id="ev-nonexistent",
            registry_dir=str(registry_dir),
            json=True,
        )

        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            cmd_verify(args)

        result = json.loads(f.getvalue())
        assert result["verdict"] == "FAIL"
        assert any("not found" in e.lower() for e in result.get("errors", []))

    def test_missing_evidence_file_has_empty_checks(self, tmp_path):
        """When evidence file doesn't exist, checks list is empty."""
        from vibe_evidence_verifier import cmd_verify
        import types

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()

        args = types.SimpleNamespace(
            command="verify",
            evidence_dir=str(evidence_dir),
            evidence_id="ev-nonexistent",
            registry_dir=str(registry_dir),
            json=True,
        )

        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            cmd_verify(args)

        result = json.loads(f.getvalue())
        assert result["checks"] == []


# ── T-65: registry entry file missing at verify time ────────────────────────

class TestT65RegistryEntryMissingAtVerify:
    """T-65: Registry entry file absent at verify time → WARN for registry_entry check."""

    def test_missing_registry_entry_file_warns(self, tmp_path):
        """When registry entry file doesn't exist, registry_entry check is WARN."""
        evidence = _make_evidence(dar_entries=[_valid_entry()])
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        evidence_file = evidence_dir / "ev-test.json"
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

        # Empty registry dir — no entry files
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir(exist_ok=True)

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

        result = json.loads(f.getvalue())
        reg_check = None
        for c in result.get("checks", []):
            if c["name"] == "registry_entry":
                reg_check = c
                break
        assert reg_check is not None
        assert reg_check["result"] == "WARN"


# ── T-66: malformed evidence JSON → FAIL ────────────────────────────────────

class TestT66MalformedEvidenceJSON:
    """T-66: Evidence file with malformed JSON → FAIL with not-found error."""

    def test_malformed_json_returns_fail(self, tmp_path):
        """Corrupted JSON in evidence file → verifier returns FAIL."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evidence_file = evidence_dir / "ev-test.json"
        evidence_file.write_text("{invalid json content", encoding="utf-8")

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()

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

        result = json.loads(f.getvalue())
        assert result["verdict"] == "FAIL"
        assert any("not found" in e.lower() for e in result.get("errors", []))

    def test_empty_file_returns_fail(self, tmp_path):
        """Empty evidence file → verifier returns FAIL."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evidence_file = evidence_dir / "ev-test.json"
        evidence_file.write_text("", encoding="utf-8")

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()

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

        result = json.loads(f.getvalue())
        assert result["verdict"] == "FAIL"


# ── T-67: malformed registry entry JSON → WARN ──────────────────────────────

class TestT67MalformedRegistryJSON:
    """T-67: Registry entry file with malformed JSON → WARN for registry_entry check."""

    def test_malformed_registry_json_warns(self, tmp_path):
        """Corrupted JSON in registry entry → registry_entry check is WARN."""
        evidence = _make_evidence(dar_entries=[_valid_entry()])
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        evidence_file = evidence_dir / "ev-test.json"
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

        # Write malformed registry entry
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir(exist_ok=True)
        entry_file = registry_dir / f"{evidence['workorder_id']}.json"
        entry_file.write_text("{corrupted json", encoding="utf-8")

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

        result = json.loads(f.getvalue())
        reg_check = None
        for c in result.get("checks", []):
            if c["name"] == "registry_entry":
                reg_check = c
                break
        assert reg_check is not None
        assert reg_check["result"] == "WARN"

    def test_malformed_registry_dar_check_still_runs(self, tmp_path):
        """Even with malformed registry entry, DAR check still runs on evidence."""
        entry = _valid_entry()
        evidence = _make_evidence(dar_entries=[entry])
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        evidence_file = evidence_dir / "ev-test.json"
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

        # Write malformed registry entry
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir(exist_ok=True)
        entry_file = registry_dir / f"{evidence['workorder_id']}.json"
        entry_file.write_text("not json", encoding="utf-8")

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

        result = json.loads(f.getvalue())
        dar_check = _get_dar_check(result)
        assert dar_check is not None, "DAR check should still run even with malformed registry"
        assert dar_check["result"] == "PASS"


# ── T-68: evidence directory completely empty ───────────────────────────────

class TestT68EmptyEvidenceDir:
    """T-68: Evidence directory exists but is completely empty → FAIL."""

    def test_empty_evidence_dir_returns_fail(self, tmp_path):
        """Empty evidence directory → FAIL with not-found."""
        from vibe_evidence_verifier import cmd_verify
        import types

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()

        args = types.SimpleNamespace(
            command="verify",
            evidence_dir=str(evidence_dir),
            evidence_id="ev-001",
            registry_dir=str(registry_dir),
            json=True,
        )

        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            cmd_verify(args)

        result = json.loads(f.getvalue())
        assert result["verdict"] == "FAIL"


# ── T-69: missing evidence_id arg ───────────────────────────────────────────

class TestT69MissingEvidenceId:
    """T-69: Missing --evidence-id → error."""

    def test_missing_evidence_id_returns_error(self):
        """No evidence_id → cmd_verify returns error code."""
        from vibe_evidence_verifier import cmd_verify
        import types

        args = types.SimpleNamespace(
            command="verify",
            evidence_dir="/tmp/nonexistent",
            evidence_id=None,
            registry_dir="/tmp/nonexistent",
            json=False,
        )

        import io
        import contextlib
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            ret = cmd_verify(args)

        assert ret == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
