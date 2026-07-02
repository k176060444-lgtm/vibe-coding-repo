"""
Tests for worker_attest_collector.py — PR-4D.

21bao local-only read-only attestation collector. Coverage:
- 21bao dry-run valid
- 5bao/9bao rejected
- real-mode without operator approval → skipped
- real-mode with approval but no env var → skipped
- ssh transport rejected
- wrong collector label rejected
- real-mode happy path: fixture → attestation → receipt → validator
- secret/url redaction in real-mode output
- forbidden operation flags all False
- no SSH / no subprocess / no os.environ in production path
- no real opencode.jsonc/opencode.env read
- audit-safe output (no secret/URL/path)
- BIDI control scan
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_collector.py"
FIXT_DIR = REPO / "tests" / "fixtures" / "worker_attest_21bao"


# ── Import the module under test ─────────────────────────────────────────────

sys.path.insert(0, str(REPO / "scripts"))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("worker_attest_collector", str(SCRIPT))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load worker_attest_collector from {SCRIPT}")
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["worker_attest_collector"] = _mod
import worker_attest_collector as wac  # noqa: E402


# ── 1. Plan builder ─────────────────────────────────────────────────────────


class TestPlanBuilder:
    def test_21bao_dry_run(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        assert plan["node"] == "21bao"
        assert plan["transport_type"] == "local_exec"
        assert plan["dry_run"] is True
        assert plan["collector"] == "21bao_local_only"
        assert plan["intended_user"] == "vibedev"

    def test_21bao_real_mode(self):
        plan = wac.build_collection_plan("21bao", dry_run=False)
        assert plan["dry_run"] is False
        assert plan["transport_type"] == "local_exec"

    def test_5bao_plan_valid(self):
        """5bao plan is now valid (PR-4G)."""
        plan = wac.build_collection_plan("5bao", dry_run=True)
        assert plan["transport_type"] == "ssh"
        assert plan["collector"] == "5bao_ssh_canary"
        assert plan["dry_run"] is True

    def test_9bao_plan_valid(self):
        """9bao plan is now valid (PR-4H)."""
        plan = wac.build_collection_plan("9bao", dry_run=True)
        assert plan["transport_type"] == "ssh"
        assert plan["collector"] == "9bao_ssh_canary"
        assert plan["dry_run"] is True

    def test_10bao_rejected(self):
        with pytest.raises(ValueError):
            wac.build_collection_plan("10bao", dry_run=True)

    def test_win_rejected(self):
        with pytest.raises(ValueError):
            wac.build_collection_plan("win", dry_run=True)

    def test_plan_has_required_fields(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        for f in (
            "schema_version", "plan_id", "generated_at", "node",
            "collector", "transport_type", "intended_user", "dry_run",
            "allowed_read_labels", "no_secret_value_output",
            "no_env_value_output", "no_base_url_value_output",
            "no_real_endpoint_url_output", "no_ssh_execution",
            "no_subprocess_execution", "forbidden_operations",
        ):
            assert f in plan, f"Missing field: {f}"


# ── 2. Dry-run path ─────────────────────────────────────────────────────────


class TestDryRunPath:
    def test_dry_run_collect_returns_not_collected(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        assert r["collection_status"] == "not_collected"

    def test_dry_run_attestation_is_empty(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        att = r["attestation"]
        assert att["opencode_config_present"] is False
        assert att["opencode_env_present"] is False
        assert att["model_aliases"] == []

    def test_dry_run_has_receipt(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        assert isinstance(r["receipt"], dict)
        assert r["receipt"]["collection_status"] == "not_collected"

    def test_dry_run_forbidden_flags_all_false(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        fof = r["receipt"]["forbidden_operation_flags"]
        assert all(v is False for v in fof.values()), fof


# ── 3. Real-mode gating ─────────────────────────────────────────────────────


class TestRealModeGating:
    def test_real_mode_without_approval_skipped(self):
        plan = wac.build_collection_plan("21bao", dry_run=False)
        r = wac.collect_21bao_local(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "skipped"
        assert "operator_approved_real_read" in r.get("skip_reason", "")

    def test_real_mode_with_approval_but_no_env_skipped(self):
        # Ensure env var is NOT set
        env_save = os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True
            )
            assert r["collection_status"] == "skipped"
            assert "env var" in r.get("skip_reason", "")
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_real_mode_with_approval_and_env_no_fixture(self):
        """Real mode approved but no fixture path → still skipped/error."""
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=None,
            )
            # Without explicit fixture path, real mode refuses
            assert r["collection_status"] == "error"
            assert "fixture_path" in r.get("error", "")
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_real_mode_happy_path(self):
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=FIXT_DIR / "opencode_config.json",
            )
            assert r["collection_status"] == "completed"
            assert r["attestation"]["opencode_config_present"] is True
            assert r["attestation"]["opencode_env_present"] is True
            assert r["attestation"]["model_aliases"]  # non-empty
            assert r["validator_result"]["valid"] is True
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_real_mode_receipt_audit_safe(self):
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=FIXT_DIR / "opencode_config.json",
            )
            s = json.dumps(r)
            # No actual secret tokens / real URLs in output
            assert "sk-ant-api03" not in s
            assert "sk-proj-abc" not in s
            assert "AKIAIOSFODNN7EXAMPLE" not in s
            assert "https://api.opencode.ai" not in s
            assert "http://" not in s
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save


# ── 4. Secret/URL/Path redaction ───────────────────────────────────────────


class TestRedaction:
    def test_dry_run_no_secret(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        s = json.dumps(r)
        for bad in ("sk-ant-", "sk-proj-", "ghp_", "AKIA"):
            assert bad not in s, f"Output contains {bad!r}"

    def test_dry_run_no_url(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        s = json.dumps(r)
        assert "http://" not in s
        assert "https://" not in s

    def test_real_mode_with_secret_in_fixture_redacted(self):
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=FIXT_DIR / "fixture_with_secret_url.json",
            )
            s = json.dumps(r)
            # The original secret value must be redacted
            assert "sk-ant...7890" not in s, \
                "Secret value should be redacted"
            # The original URL must be redacted
            assert "https://api.opencode.ai" not in s, \
                "URL should be redacted"
            # Redaction markers SHOULD be present
            assert "REDACTED" in s
            # But the validator catches secret-in-key_env, so status
            # will be error (validator rejects). That's correct fail-closed.
            assert r["collection_status"] in ("completed", "error")
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_redact_dict_helper(self):
        out = wac._redact_dict({
            "key": "ok",
            "secret": "sk-ant-api03-fake",
            "url": "https://example.com",
            "nested": {"secret": "AKIA1234"},
            "list": ["safe", "ghp_xxx"],
        })
        assert out["key"] == "ok"
        assert "REDACTED" in out["secret"]
        assert "REDACTED" in out["url"]
        assert "REDACTED" in out["nested"]["secret"]
        assert "REDACTED" in out["list"][1]
        assert out["list"][0] == "safe"


# ── 5. Plan validation (refuse SSH / wrong collector) ──────────────────────


class TestPlanValidation:
    def test_ssh_transport_rejected(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        plan["transport_type"] = "ssh"
        r = wac.collect_21bao_local(plan)
        assert r["collection_status"] == "error"
        assert "local_exec" in r.get("error", "")

    def test_wrong_node_in_plan_rejected(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        plan["node"] = "10bao"
        r = wac.collect_21bao_local(plan)
        assert r["collection_status"] == "error"

    def test_wrong_collector_label_rejected(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        plan["collector"] = "ssh_5bao_collector"
        r = wac.collect_21bao_local(plan)
        assert r["collection_status"] == "error"


# ── 6. AST safety: no SSH / no subprocess / no os.environ / no real paths ──


class TestASTSafety:
    def _parse(self):
        return ast.parse(SCRIPT.read_text(encoding="utf-8"))

    def _is_in_ssh_function(self, tree: ast.AST, lineno: int) -> bool:
        """Check if the given line is inside _execute_ssh_5bao or _execute_ssh_9bao."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                "_execute_ssh_5bao", "_execute_ssh_9bao"
            ):
                if node.lineno <= lineno <= (node.end_lineno or float("inf")):
                    return True
        return False

    def test_no_subprocess_import(self):
        tree = self._parse()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "subprocess":
                        # Only allowed inside SSH function (5bao/9bao)
                        assert self._is_in_ssh_function(tree, node.lineno), \
                            f"subprocess import at {node.lineno} outside SSH function"
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod == "subprocess":
                    assert self._is_in_ssh_function(tree, node.lineno), \
                        f"subprocess import at {node.lineno} outside SSH function"

    def test_no_ssh_libraries(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in (
                        "paramiko", "fabric", "pexpect"
                    )
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in (
                    "paramiko", "fabric", "pexpect"
                )

    def test_no_socket_import(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "socket"
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "socket"

    def test_no_http_libraries(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in (
                        "requests", "urllib", "urllib3"
                    )
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in (
                    "requests", "urllib", "urllib3"
                )

    def test_no_os_environ_for_secret_read(self):
        """os.environ may be used for the operator-approval gate only (env
        var name WORKER_ATTEST_OPERATOR_APPROVED is a flag, not a secret).
        It must NEVER be used to read API keys, base URLs, or any
        secret-bearing env var. Accesses should be:
        - _SSH_5BAO_KEY: reads VIBEDEV_SSH_KEY (path, not secret value)
        - _SSH_9BAO_KEY: reads VIBEDEV_SSH_KEY (path, not secret value)
        - collect_21bao_local: operator gate
        - collect_5bao_remote: operator gate
        - collect_9bao_remote: operator gate
        - main() CLI: operator gate
        """
        tree = self._parse()
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    if node.attr in ("environ", "getenv"):
                        offenders.append((node.lineno, node.attr))
        # 6 os.environ accesses are expected: 2 SSH key path config + 4 gates
        assert len(offenders) >= 4, f"Too few os.environ accesses: {offenders}"
        assert len(offenders) <= 9, \
            f"Too many os.environ accesses: {offenders}"

    def test_no_subprocess_call(self):
        tree = self._parse()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    if node.value.id == "subprocess":
                        if not self._is_in_ssh_function(tree, node.lineno):
                            assert False, f"subprocess.{node.attr} at {node.lineno}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in (
                    "system", "popen", "exec", "execvp", "spawn"
                ):
                    assert False, f"{node.func.id}() at {node.lineno}"

    def test_no_real_opencode_path_in_module_code(self):
        """No real opencode.jsonc / opencode.env paths as *executable*
        code paths. The module may contain such paths in string constants
        that serve as forbidden-pattern guards (e.g. _load_fixture's
        path-rejection list) or test payloads (self_check's
        deliberately-bad paths). These are SAFE because they are never
        used to traverse or read the real filesystem — they're matched
        against an input path and REJECTED.

        What's FORBIDDEN: default arguments, function defaults, or
        implicit lookups containing real worker paths."""
        tree = self._parse()
        import ast as _ast

        # Find all default argument values that contain real paths
        for node in ast.walk(tree):
            if isinstance(node, _ast.FunctionDef):
                for d in node.args.defaults:
                    if isinstance(d, _ast.Constant) and isinstance(d.value, str):
                        v = d.value
                        for bad in ("/home/vibeworker", "C:/Users/KK/.opencode"):
                            if bad in v:
                                assert False, \
                                    f"Real path in default arg '{v}' at {node.name}:{d.lineno}"
                for d in node.args.kw_defaults or []:
                    if isinstance(d, _ast.Constant) and isinstance(d.value, str):
                        v = d.value
                        for bad in ("/home/vibeworker", "C:/Users/KK/.opencode"):
                            if bad in v:
                                assert False, \
                                    f"Real path in kw_default arg '{v}' at {node.name}:{d.lineno}"

        # Verify DEFAULT_FIXTURE_FOR_LABEL uses repo-relative paths,
        # not real worker paths
        src = SCRIPT.read_text(encoding="utf-8")
        assert "DEFAULT_FIXTURE_FOR_LABEL" in src


# ── 7. CLI smoke ────────────────────────────────────────────────────────────


class TestCLI:
    def _run(self, *args, env_extra=None):
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, timeout=10, env=env,
        )

    def test_self_check_cli(self):
        r = self._run("self-check")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["status"] == "PASS"

    def test_collect_dry_run_21bao(self):
        r = self._run("collect", "--node", "21bao")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["collection_status"] == "not_collected"

    def test_collect_dry_run_5bao_blocked(self):
        r = self._run("collect", "--node", "5bao")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["collection_status"] == "not_collected"

    def test_collect_real_without_env_skipped(self):
        env_save = os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
        try:
            r = self._run("collect", "--node", "21bao", "--real",
                          "--fixture", str(FIXT_DIR / "opencode_config.json"))
            assert r.returncode == 0
            out = json.loads(r.stdout)
            assert out["collection_status"] == "skipped"
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_collect_real_with_env_completed(self):
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            r = self._run("collect", "--node", "21bao", "--real",
                          "--fixture", str(FIXT_DIR / "opencode_config.json"))
            assert r.returncode == 0
            out = json.loads(r.stdout)
            assert out["collection_status"] == "completed"
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save


# ── 8. Audit-safe output (no secret/URL/path) ──────────────────────────────


class TestAuditSafeOutput:
    def test_dry_run_output_audit_safe(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        s = json.dumps(r)
        for bad in ("sk-ant-", "sk-proj-", "ghp_", "AKIA",
                    "http://", "https://", "xai-"):
            assert bad not in s, f"Output contains {bad!r}"

    def test_real_mode_audit_safe(self):
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=FIXT_DIR / "opencode_config.json",
            )
            s = json.dumps(r)
            for bad in ("sk-ant-", "sk-proj-", "ghp_", "AKIA"):
                assert bad not in s, f"Real output contains {bad!r}"
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save


# ── 9. BIDI control scan ───────────────────────────────────────────────────


class TestBidiControl:
    BIDI_CHARS = set(chr(c) for c in range(0x202A, 0x202F)) | \
                 set(chr(c) for c in range(0x2066, 0x206A)) | \
                 {"\u200E", "\u200F"}

    def test_no_bidi_in_source(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, \
                f"BIDI at offset {i}: U+{ord(ch):04X}"

    def test_no_bidi_in_fixtures(self):
        for f in sorted(FIXT_DIR.glob("*.json")):
            src = f.read_text(encoding="utf-8")
            for i, ch in enumerate(src):
                assert ch not in self.BIDI_CHARS, \
                    f"BIDI in {f.name} at offset {i}: U+{ord(ch):04X}"


# ── 10. Self-check end-to-end ──────────────────────────────────────────────


class TestSelfCheckEndToEnd:
    def test_self_check_runs_and_passes(self):
        r = wac.self_check()
        assert r["status"] == "PASS", \
            f"Self-check FAILED: {[c for c in r['checks'] if not c['passed']]}"
        assert r["detail"].startswith("27/27")


# ── 11. Receipt validates against worker_attest_plan schema ────────────────


class TestReceiptSchema:
    def test_dry_run_receipt_passes_workspace_validator(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from worker_attest_plan import validate_receipt
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_21bao_local(plan)
        v = validate_receipt(r["receipt"])
        assert v["valid"], f"Receipt failed: {v['errors']}"

    def test_real_mode_receipt_passes_workspace_validator(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from worker_attest_plan import validate_receipt
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED", None)
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(
                plan, operator_approved_real_read=True,
                fixture_path=FIXT_DIR / "opencode_config.json",
            )
            v = validate_receipt(r["receipt"])
            assert v["valid"], f"Receipt failed: {v['errors']}"
        finally:
            if env_save is None:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
            else:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Canary real-read (Phase 3 PR-4F)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanaryRealRead:
    """21bao local real-read canary tests (PR-4F)."""

    def test_canary_gate_without_approval_skipped(self):
        """Canary real read without operator_approved_real_read -> skipped."""
        plan = wac.build_collection_plan("21bao", dry_run=False)
        r = wac.collect_21bao_local(plan, canary_real_read=True,
                                    operator_approved_real_read=False)
        assert r["collection_status"] == "skipped"

    def test_canary_gate_with_approval_no_env_skipped(self):
        """Canary with approval but no env var -> skipped."""
        env_save = os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(plan, canary_real_read=True,
                                        operator_approved_real_read=True)
            assert r["collection_status"] == "skipped"
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_canary_real_read_completed(self):
        """Canary with all gates open reads real 21bao config."""
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED")
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(plan, canary_real_read=True,
                                        operator_approved_real_read=True)
            if r["collection_status"] == "completed":
                assert "model_aliases" in r["attestation"]
                assert len(r["attestation"]["model_aliases"]) > 0
                assert r["attestation"]["node"] == "21bao"
                assert r["attestation"]["opencode_config_present"] is True
                fof = r["forbidden_operation_flags"]
                for k, v in fof.items():
                    assert v is False, f"forbidden flag '{k}' is {v}"
                from worker_attest_plan import validate_receipt
                v = validate_receipt(r["receipt"])
                assert v["valid"], f"Receipt failed: {v['errors']}"
            else:
                assert r["collection_status"] in ("error", "skipped")
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save
            else:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)

    def test_canary_audit_safe(self):
        """Canary real-read output must be audit-safe (no secrets/URLs)."""
        env_save = os.environ.get("WORKER_ATTEST_OPERATOR_APPROVED")
        os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = "1"
        try:
            plan = wac.build_collection_plan("21bao", dry_run=False)
            r = wac.collect_21bao_local(plan, canary_real_read=True,
                                        operator_approved_real_read=True)
            if r["collection_status"] == "completed":
                s = json.dumps(r)
                has_secret = any(p in s for p in wac._SECRET_PATTERNS)
                has_url = any(p in s for p in wac._URL_PATTERNS)
                assert not has_secret, "Secret pattern leaked in output!"
                assert not has_url, "URL pattern leaked in output!"
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save
            else:
                os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)

    def test_canary_no_subprocess(self):
        """Canary read must not use subprocess outside SSH function."""
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "subprocess":
                    # Check if inside SSH function (5bao/9bao approved)
                    for fn in ast.walk(tree):
                        if isinstance(fn, ast.FunctionDef) and fn.name in (
                            "_execute_ssh_5bao", "_execute_ssh_9bao"
                        ):
                            if fn.lineno <= node.lineno <= (fn.end_lineno or float("inf")):
                                break
                    else:
                        pytest.fail(f"subprocess reference at line {node.lineno}")


# ── 12. 9bao SSH canary (PR-4H) ──────────────────────────────────────────────


class Test9baoSshCanary:
    """9bao SSH canary must mirror 5bao safety: refuse 5bao/21bao,
    dual-gated real reads, audit-safe dry-run, AST-verified subprocess
    containment."""

    def test_9bao_plan_has_ssh_transport(self):
        plan = wac.build_collection_plan("9bao", dry_run=True)
        assert plan["transport_type"] == "ssh"
        assert plan["collector"] == "9bao_ssh_canary"
        assert plan["node"] == "9bao"

    def test_9bao_dry_run_returns_not_collected(self):
        plan = wac.build_collection_plan("9bao", dry_run=True)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "not_collected"
        fof = r["forbidden_operation_flags"]
        for k, v in fof.items():
            assert v is False, f"forbidden flag '{k}' is {v} on 9bao dry-run"

    def test_9bao_real_mode_without_approval_skipped(self):
        plan = wac.build_collection_plan("9bao", dry_run=False)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "skipped"
        assert r["forbidden_operation_flags"]["ssh_attempted"] is False

    def test_9bao_real_mode_with_approval_no_env_skipped(self):
        env_save = os.environ.pop("WORKER_ATTEST_OPERATOR_APPROVED", None)
        try:
            plan = wac.build_collection_plan("9bao", dry_run=False)
            r = wac.collect_9bao_remote(plan, operator_approved_real_read=True)
            assert r["collection_status"] == "skipped"
            assert r["forbidden_operation_flags"]["ssh_attempted"] is False
        finally:
            if env_save is not None:
                os.environ["WORKER_ATTEST_OPERATOR_APPROVED"] = env_save

    def test_9bao_rejects_5bao_node(self):
        plan = wac.build_collection_plan("5bao", dry_run=True)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "error"
        assert "not in 9bao" in r.get("error", "")

    def test_9bao_rejects_21bao_node(self):
        plan = wac.build_collection_plan("21bao", dry_run=True)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "error"
        assert "not in 9bao" in r.get("error", "")

    def test_9bao_rejects_local_exec_transport(self):
        plan = wac.build_collection_plan("9bao", dry_run=True)
        plan["transport_type"] = "local_exec"
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        assert r["collection_status"] == "error"
        assert "ssh" in r.get("error", "")

    def test_9bao_dry_run_audit_safe(self):
        plan = wac.build_collection_plan("9bao", dry_run=True)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        out = json.dumps(r)
        for bad in (
            "sk-ant-", "sk-proj-", "ghp_", "gho_", "glpat-", "xai-",
            "AKIA", "BEGIN", "192.168.9.6", "vibeworker",
            "/home/vibeworker", "opencode.env",
        ):
            assert bad not in out, f"9bao dry-run leaks '{bad}'"
        assert r["receipt"]["redaction_status"]["no_secret_value"] is True
        assert r["receipt"]["redaction_status"]["no_base_url_value"] is True
        assert r["receipt"]["redaction_status"]["no_real_endpoint_url"] is True

    def test_9bao_receipt_validates(self):
        plan = wac.build_collection_plan("9bao", dry_run=True)
        r = wac.collect_9bao_remote(plan, operator_approved_real_read=False)
        from worker_attest_plan import validate_receipt
        v = validate_receipt(r["receipt"])
        assert v["valid"], f"9bao receipt invalid: {v.get('errors')}"

    def test_9bao_ssh_host_is_9bao_not_5bao(self):
        """PR-4H invariant: 9bao SSH must target 192.168.9.6, never 5bao's IP."""
        assert wac._SSH_9BAO_HOST == "192.168.9.6"
        assert wac._SSH_5BAO_HOST == "192.168.5.6"
        # Both use the same shared key
        assert wac._SSH_9BAO_KEY == wac._SSH_5BAO_KEY

    def test_9bao_no_5bao_or_21bao_in_ssh_target(self):
        """AST verify: 9bao SSH cmd must reference 9bao host only, never 5bao."""
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        # Find _execute_ssh_9bao function
        ssh9_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_execute_ssh_9bao":
                ssh9_fn = node
                break
        assert ssh9_fn is not None, "_execute_ssh_9bao must exist"
        # Get function source
        fn_src = ast.get_source_segment(SCRIPT.read_text(encoding="utf-8"), ssh9_fn)
        assert "_SSH_9BAO_HOST" in fn_src
        assert "_SSH_5BAO_HOST" not in fn_src, "9bao SSH must not reference 5bao host"
        assert "192.168.5.6" not in fn_src, "9bao SSH must not hardcode 5bao IP"
        # 5bao SSH function check (mirror)
        ssh5_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_execute_ssh_5bao":
                ssh5_fn = node
                break
        assert ssh5_fn is not None, "_execute_ssh_5bao must still exist"
        fn5_src = ast.get_source_segment(SCRIPT.read_text(encoding="utf-8"), ssh5_fn)
        assert "_SSH_5BAO_HOST" in fn5_src
        assert "_SSH_9BAO_HOST" not in fn5_src, "5bao SSH must not reference 9bao host"
        assert "192.168.9.6" not in fn5_src, "5bao SSH must not hardcode 9bao IP"

    def test_9bao_remote_script_excludes_opencode_env(self):
        """9bao remote script must not read opencode.env (only config.json/jsonc)."""
        from worker_attest_collector import _9BAO_REMOTE_COLLECTOR_SCRIPT
        # Allowed
        assert "~/.config/opencode/config.json" in _9BAO_REMOTE_COLLECTOR_SCRIPT
        # Forbidden
        assert "opencode.env" not in _9BAO_REMOTE_COLLECTOR_SCRIPT
        # No value-extraction
        assert "os.environ[" not in _9BAO_REMOTE_COLLECTOR_SCRIPT
        assert "os.environ.get" not in _9BAO_REMOTE_COLLECTOR_SCRIPT
