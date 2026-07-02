"""
Tests for worker_attest_plan.py — PR-4C.

Coverage:
- 21bao local-exec command plan valid
- 5bao ssh command plan valid
- 9bao ssh command plan valid
- invalid node blocked
- 21bao as ssh blocked
- 5bao/9bao as local_exec blocked (without operator override)
- operator override allowed for 5bao/9bao
- command execution forbidden (no real paths, no SSH fragments)
- secret/url/env value redaction
- receipt schema valid + missing field blocked
- no subprocess / os.environ in production path
- no real opencode.jsonc/opencode.env read
- audit-safe output
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_plan.py"
FIXT_DIR = REPO / "tests" / "fixtures" / "worker_attest_plan"

# Make the module importable
sys.path.insert(0, str(REPO / "scripts"))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("worker_attest_plan", str(SCRIPT))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load worker_attest_plan from {SCRIPT}")
_wap_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_wap_mod)
sys.modules["worker_attest_plan"] = _wap_mod
import worker_attest_plan as wap  # noqa: E402


# ── 1. Valid command plans ───────────────────────────────────────────────────


class TestValidCommandPlans:
    """21bao/5bao/9bao plans must each produce a valid dry-run template."""

    def test_21bao_local_exec(self):
        plan = wap.build_command_plan("21bao")
        r = wap.validate_command_plan(plan)
        assert r["valid"], f"21bao plan failed: {r['errors']}"
        assert plan["transport_type"] == "local_exec"
        assert plan["node"] == "21bao"
        assert plan["intended_user"] == "vibedev"

    def test_5bao_ssh(self):
        plan = wap.build_command_plan("5bao")
        r = wap.validate_command_plan(plan)
        assert r["valid"], f"5bao plan failed: {r['errors']}"
        assert plan["transport_type"] == "ssh"
        assert plan["node"] == "5bao"
        assert plan["intended_user"] == "vibeworker"

    def test_9bao_ssh(self):
        plan = wap.build_command_plan("9bao")
        r = wap.validate_command_plan(plan)
        assert r["valid"], f"9bao plan failed: {r['errors']}"
        assert plan["transport_type"] == "ssh"
        assert plan["node"] == "9bao"
        assert plan["intended_user"] == "vibeworker"

    def test_plan_has_required_fields(self):
        plan = wap.build_command_plan("21bao")
        for f in (
            "schema_version", "plan_id", "generated_at", "node",
            "transport_type", "intended_user", "allowed_read_paths",
            "output_path_label", "receipt_path_label", "safety_flags",
            "no_secret_value_output", "no_env_value_output",
            "no_base_url_value_output", "no_real_endpoint_url_output",
            "command_template",
        ):
            assert f in plan, f"Missing field: {f}"

    def test_plan_safety_flags_all_set(self):
        for node in ("21bao", "5bao", "9bao"):
            plan = wap.build_command_plan(node)
            for flag in (
                "no_secret_value_output", "no_env_value_output",
                "no_base_url_value_output", "no_real_endpoint_url_output",
            ):
                assert plan[flag] is True, f"{node}.{flag} must be True"
            for flag in wap.SAFETY_FLAGS:
                assert flag in plan["safety_flags"], \
                    f"{node} safety_flags missing {flag}"


# ── 2. Invalid node ──────────────────────────────────────────────────────────


class TestInvalidNode:
    def test_invalid_node_raises(self):
        with pytest.raises(ValueError):
            wap.build_command_plan("10bao")

    def test_invalid_node_hermes(self):
        with pytest.raises(ValueError):
            wap.build_command_plan("hermes")

    def test_invalid_node_win(self):
        # win is legacy alias, NOT a valid direct node input here
        with pytest.raises(ValueError):
            wap.build_command_plan("win")


# ── 3. 21bao must NOT be SSH ────────────────────────────────────────────────


class Test21baoMustBeLocalExec:
    def test_21bao_as_ssh_blocked(self):
        plan = wap.build_command_plan("21bao")
        plan["transport_type"] = "ssh"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]
        assert any("local_exec" in e for e in r["errors"])
        assert any("21bao" in e for e in r["errors"])

    def test_21bao_with_override_still_local(self):
        # override flag has no effect for 21bao; must still be local_exec
        plan = wap.build_command_plan(
            "21bao", operator_override_local_exec_for_remote=True
        )
        assert plan["transport_type"] == "local_exec"
        r = wap.validate_command_plan(plan)
        assert r["valid"]


# ── 4. 5bao/9bao as local_exec requires override ────────────────────────────


class TestRemoteNodeTransport:
    def test_5bao_as_local_exec_blocked_without_override(self):
        plan = wap.build_command_plan("5bao")
        plan["transport_type"] = "local_exec"
        plan["operator_override_local_exec_for_remote"] = False
        r = wap.validate_command_plan(plan)
        assert not r["valid"]
        assert any("operator_override" in e or "remote" in e
                   for e in r["errors"])

    def test_9bao_as_local_exec_blocked_without_override(self):
        plan = wap.build_command_plan("9bao")
        plan["transport_type"] = "local_exec"
        plan["operator_override_local_exec_for_remote"] = False
        r = wap.validate_command_plan(plan)
        assert not r["valid"]

    def test_5bao_local_exec_with_override_allowed(self):
        plan = wap.build_command_plan(
            "5bao", operator_override_local_exec_for_remote=True
        )
        r = wap.validate_command_plan(plan)
        assert r["valid"]
        # Should produce a warning (forward-compat)
        assert any("override" in w.lower() for w in r["warnings"])

    def test_5bao_unknown_transport_blocked(self):
        plan = wap.build_command_plan("5bao")
        plan["transport_type"] = "ftp"  # not a valid transport
        r = wap.validate_command_plan(plan)
        assert not r["valid"]


# ── 5. Command execution forbidden ──────────────────────────────────────────


class TestCommandExecutionForbidden:
    def test_ssh_fragment_in_command_blocked(self):
        plan = wap.build_command_plan("5bao")
        plan["command_template"]["shell"] = "ssh vibeworker@5bao cat ~/.opencode"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]
        assert any("ssh " in e for e in r["errors"])

    def test_subprocess_fragment_in_command_blocked(self):
        plan = wap.build_command_plan("5bao")
        plan["command_template"]["shell"] = "subprocess.run(['ls'])"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]

    def test_real_path_in_output_blocked(self):
        plan = wap.build_command_plan("21bao")
        plan["output_path"] = "C:/Users/KK/.opencode/config.json"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]

    def test_real_path_in_receipt_path_blocked(self):
        plan = wap.build_command_plan("21bao")
        plan["receipt_path"] = "/home/vibeworker/.opencode/receipt.json"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]

    def test_curl_fragment_blocked(self):
        plan = wap.build_command_plan("5bao")
        plan["command_template"]["shell"] = "curl -X POST https://api"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]


# ── 6. Secret/URL/Env redaction ─────────────────────────────────────────────


class TestRedaction:
    def test_secret_in_plan_blocked(self):
        plan = wap.build_command_plan("21bao")
        plan["command_template"]["secret"] = "sk-ant-api03-1234567890"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]
        assert any("secret" in e.lower() for e in r["errors"])

    def test_url_in_plan_blocked(self):
        plan = wap.build_command_plan("21bao")
        plan["command_template"]["endpoint"] = "https://api.opencode.ai/zen/go/v1"
        r = wap.validate_command_plan(plan)
        assert not r["valid"]
        assert any("URL" in e for e in r["errors"])

    def test_safe_string_in_plan_allowed(self):
        plan = wap.build_command_plan("21bao")
        plan["command_template"]["note"] = "This is a safe descriptive note"
        r = wap.validate_command_plan(plan)
        assert r["valid"]


# ── 7. Receipt schema valid + missing field ─────────────────────────────────


class TestReceiptSchema:
    def test_valid_21bao_receipt(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        r = wap.validate_receipt(receipt)
        assert r["valid"], f"Receipt failed: {r['errors']}"

    def test_valid_5bao_receipt(self):
        plan = wap.build_command_plan("5bao")
        receipt = wap.build_receipt_template("5bao", plan["plan_id"])
        r = wap.validate_receipt(receipt)
        assert r["valid"]

    def test_missing_command_plan_id_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        del receipt["command_plan_id"]
        r = wap.validate_receipt(receipt)
        assert not r["valid"]
        assert any("command_plan_id" in e for e in r["errors"])

    def test_missing_redaction_status_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        del receipt["redaction_status"]
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_wrong_source_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["source"] = "manual_hack"
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_invalid_node_in_receipt_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["node"] = "10bao"
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_real_path_in_attestation_file_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["attestation_file"] = "C:/real/opencode.jsonc"
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_redaction_flag_false_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["redaction_status"]["no_secret_value"] = False
        r = wap.validate_receipt(receipt)
        assert not r["valid"]


# ── 8. Forbidden operation flags in receipt ─────────────────────────────────


class TestForbiddenFlagsInReceipt:
    def test_ssh_attempted_flag_blocked(self):
        plan = wap.build_command_plan("5bao")
        receipt = wap.build_receipt_template("5bao", plan["plan_id"])
        receipt["forbidden_operation_flags"]["ssh_attempted"] = True
        r = wap.validate_receipt(receipt)
        assert not r["valid"]
        assert any("ssh_attempted" in e for e in r["errors"])

    def test_subprocess_attempted_flag_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["forbidden_operation_flags"]["subprocess_attempted"] = True
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_model_call_attempted_flag_blocked(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        receipt["forbidden_operation_flags"]["model_call_attempted"] = True
        r = wap.validate_receipt(receipt)
        assert not r["valid"]

    def test_credential_provisioning_attempted_blocked(self):
        plan = wap.build_command_plan("5bao")
        receipt = wap.build_receipt_template("5bao", plan["plan_id"])
        receipt["forbidden_operation_flags"]["credential_provisioning_attempted"] = True
        r = wap.validate_receipt(receipt)
        assert not r["valid"]


# ── 9. AST safety: no subprocess / os.environ / no real worker access ──────


class TestASTSafety:
    """Production module must not import or call forbidden APIs."""

    def _parse(self):
        return ast.parse(SCRIPT.read_text(encoding="utf-8"))

    def test_no_subprocess_import(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "subprocess"
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "subprocess"

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

    def test_no_os_environ_in_module(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "") == "os":
                    for alias in node.names:
                        assert alias.name not in ("environ", "getenv")
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    assert node.attr not in ("environ", "getenv")

    def test_no_subprocess_call_in_module(self):
        for node in ast.walk(self._parse()):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    if node.value.id == "subprocess":
                        assert False, "subprocess attribute access in module"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id == "subprocess":
                            assert False, "subprocess() call in module"
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in (
                        "system", "popen", "exec", "execvp", "spawn"
                    )

    def test_no_real_opencode_config_read(self):
        """Module must not read real opencode.jsonc paths."""
        content = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("opencode.jsonc", "opencode.env"):
            assert forbidden not in content, \
                f"Production module mentions {forbidden} (real path)"

    def test_no_real_home_path_in_code(self):
        """No hard-coded real home paths as bare string literals in the
        module AST. We allow them in test fixtures (assertion payloads
        that are themselves tests for redaction)."""
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                for forbidden in (
                    "/home/vibeworker", "C:/Users/KK/.opencode",
                    "C:\\\\Users\\\\KK\\\\.opencode",
                ):
                    if forbidden in v:
                        offenders.append((node.lineno, forbidden, v[:60]))
        assert not offenders, \
            f"Hard-coded real paths in module: {offenders}"


# ── 10. CLI smoke ───────────────────────────────────────────────────────────


class TestCLI:
    """Smoke test the CLI entry points."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_self_check_cli(self):
        r = self._run("self-check")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["status"] == "PASS"

    def test_plan_21bao_cli(self):
        r = self._run("plan", "--node", "21bao")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["node"] == "21bao"
        assert out["transport_type"] == "local_exec"

    def test_plan_5bao_cli(self):
        r = self._run("plan", "--node", "5bao")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["node"] == "5bao"
        assert out["transport_type"] == "ssh"

    def test_plan_9bao_cli(self):
        r = self._run("plan", "--node", "9bao")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["node"] == "9bao"
        assert out["transport_type"] == "ssh"

    def test_plan_invalid_node_cli(self):
        r = self._run("plan", "--node", "10bao")
        assert r.returncode != 0
        out = json.loads(r.stdout)
        assert "10bao" in out["error"] or "Unknown" in out["error"]

    def test_validate_receipt_21bao_valid(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_21bao_valid.json"),
        )
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["valid"] is True

    def test_validate_receipt_5bao_valid(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_5bao_valid.json"),
        )
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["valid"] is True

    def test_validate_receipt_invalid_node_blocked(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_invalid_node.json"),
        )
        assert r.returncode != 0
        out = json.loads(r.stdout)
        assert out["valid"] is False

    def test_validate_receipt_ssh_attempted_blocked(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_ssh_attempted.json"),
        )
        assert r.returncode != 0
        out = json.loads(r.stdout)
        assert out["valid"] is False

    def test_validate_receipt_real_path_blocked(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_real_path.json"),
        )
        assert r.returncode != 0
        out = json.loads(r.stdout)
        assert out["valid"] is False

    def test_validate_receipt_redaction_fail_blocked(self):
        r = self._run(
            "validate-receipt",
            "--file", str(FIXT_DIR / "receipt_redaction_fail.json"),
        )
        assert r.returncode != 0
        out = json.loads(r.stdout)
        assert out["valid"] is False

    def test_validate_receipt_missing_file(self):
        r = self._run(
            "validate-receipt", "--file", str(FIXT_DIR / "nonexistent.json")
        )
        assert r.returncode != 0


# ── 11. Audit-safe output ───────────────────────────────────────────────────


class TestAuditSafeOutput:
    def test_plan_output_no_secret(self):
        plan = wap.build_command_plan("21bao")
        s = json.dumps(plan)
        for bad in ("sk-ant-", "sk-proj-", "ghp_", "AKIA", "BEGIN"):
            assert bad not in s, f"Plan contains secret-like {bad!r}"

    def test_plan_output_no_url(self):
        plan = wap.build_command_plan("5bao")
        s = json.dumps(plan)
        assert "http://" not in s
        assert "https://" not in s

    def test_receipt_output_no_secret(self):
        plan = wap.build_command_plan("21bao")
        receipt = wap.build_receipt_template("21bao", plan["plan_id"])
        s = json.dumps(receipt)
        for bad in ("sk-ant-", "sk-proj-", "ghp_", "AKIA"):
            assert bad not in s, f"Receipt contains secret-like {bad!r}"

    def test_receipt_output_no_url(self):
        plan = wap.build_command_plan("5bao")
        receipt = wap.build_receipt_template("5bao", plan["plan_id"])
        s = json.dumps(receipt)
        assert "http://" not in s
        assert "https://" not in s

    def test_validation_error_messages_no_values(self):
        """Error messages should reference field names, not echo values."""
        plan = wap.build_command_plan("21bao")
        plan["command_template"]["secret"] = "sk-ant-api03-1234567890"
        r = wap.validate_command_plan(plan)
        # The error must mention "secret" but NOT echo the actual value
        assert any("secret" in e.lower() for e in r["errors"])
        for err in r["errors"]:
            assert "sk-ant-api03" not in err, \
                f"Error leaks value: {err}"


# ── 12. BIDI control scan ───────────────────────────────────────────────────


class TestBidiControl:
    """Source file must not contain hidden bidi control characters."""

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


# ── 13. Self-check end-to-end ───────────────────────────────────────────────


class TestSelfCheckEndToEnd:
    def test_self_check_runs_and_passes(self):
        r = wap.self_check()
        assert r["status"] == "PASS", \
            f"Self-check FAILED: {[c for c in r['checks'] if not c['passed']]}"
        # All 15 self-checks must pass
        assert r["detail"].startswith("15/15")


# ── 14. Collection status taxonomy ──────────────────────────────────────────


class TestCollectionStatus:
    def test_valid_statuses(self):
        for s in ("not_collected", "skipped", "error", "completed"):
            r = wap.build_receipt_template("21bao", "plan_x", collection_status=s)
            v = wap.validate_receipt(r)
            assert v["valid"], f"{s} should be valid"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            wap.build_receipt_template("21bao", "plan_x", collection_status="totally_executed")
