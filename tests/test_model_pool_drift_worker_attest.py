#!/usr/bin/env python3
"""Tests for drift Layer 2 — worker_attest fixture adapter (Phase 3 PR-4B).

Covers:
- Valid 21bao/5bao/9bao fixtures produce 0 blocking drift
- Missing fixture blocks
- Node mismatch blocks
- Alias missing warns
- Extra alias warns/block rules
- Provider namespace mismatch blocks
- Lifecycle status mismatch blocks
- Credential/endpoint_ref mismatch warns
- Secret/URL values remain redacted
- No SSH / no subprocess / no os.environ
- Audit-safe output
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXT_DIR = REPO / "tests" / "fixtures" / "worker_attest"
SCRIPT = REPO / "scripts" / "model_pool_drift.py"

# ── Helpers ──────────────────────────────────────────────────────────────────


def _run_layer2(*args: str) -> dict:
    """Run model_pool_drift.py layer2 with given args; return parsed JSON."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "layer2", *args],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


def _has_category(report: dict, cat: str) -> bool:
    return cat in report.get("drift_categories", []) or cat in report.get("warn_categories", [])


def _block_count(report: dict) -> int:
    return report.get("drift_count", 0)


def _warn_count(report: dict) -> int:
    return report.get("warn_count", 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Valid fixtures — 0 blocking drift
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidFixtures:
    """Valid fixtures must have 0 blocking drift."""

    def test_21bao_no_blocking(self):
        r = _run_layer2("--node", "21bao")
        assert r["layer"] == 2
        assert _block_count(r) == 0, f"21bao has blocking drift: {r['drift_categories']}"
        assert r["node"] == "21bao"

    def test_5bao_no_blocking(self):
        r = _run_layer2("--node", "5bao")
        assert _block_count(r) == 0
        assert r["node"] == "5bao"

    def test_9bao_no_blocking(self):
        r = _run_layer2("--node", "9bao")
        assert _block_count(r) == 0
        assert r["node"] == "9bao"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Missing fixture / missing node
# ═══════════════════════════════════════════════════════════════════════════════

class TestMissingFixture:
    """Missing fixture must produce worker_attest_missing."""

    def test_missing_node_blocks(self):
        r = _run_layer2("--node", "10bao")
        assert _block_count(r) >= 1
        assert "worker_attest_missing" in r["drift_categories"]

    def test_no_arg_blocks(self):
        r = _run_layer2()
        assert _block_count(r) >= 1
        assert "worker_attest_missing" in r["drift_categories"]

    def test_custom_path_missing_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "nonexistent.json"))
        assert _block_count(r) >= 1
        assert "worker_attest_missing" in r["drift_categories"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Invalid fixture detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidFixture:
    """Invalid fixtures must be detected by Layer 2."""

    def test_invalid_node_fixture_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "worker_attest_invalid_node.json"))
        assert _block_count(r) >= 1
        assert _has_category(r, "worker_attestation_invalid")

    def test_missing_field_fixture_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "worker_attest_missing_field.json"))
        assert _block_count(r) >= 1
        assert _has_category(r, "worker_attestation_invalid")

    def test_old_schema_fixture_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "worker_attest_old_schema.json"))
        assert _block_count(r) >= 1
        assert _has_category(r, "worker_attestation_invalid")

    def test_secret_leak_fixture_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "worker_attest_secret_leak.json"))
        assert _block_count(r) >= 1
        assert _has_category(r, "worker_attestation_invalid")

    def test_url_leak_fixture_blocks(self):
        r = _run_layer2("--fixture", str(FIXT_DIR / "worker_attest_url_leak.json"))
        assert _block_count(r) >= 1
        assert _has_category(r, "worker_attestation_invalid")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WARN-only checks for valid fixtures
# ═══════════════════════════════════════════════════════════════════════════════

class TestWarnCategories:
    """Valid fixtures may produce WARNs but never BLOCKs."""

    def test_21bao_has_alias_missing_warns(self):
        r = _run_layer2("--node", "21bao")
        assert _warn_count(r) > 0
        assert "worker_alias_missing" in r["warn_categories"]
        # Verify no extra_alias (fixture models should all be in pool/matrix)
        assert "worker_extra_alias" not in r["warn_categories"]

    def test_warns_not_elevated_to_block(self):
        """Assert that none of the WARN categories are in BLOCK categories."""
        r = _run_layer2("--node", "21bao")
        for wc in r.get("warn_categories", []):
            assert wc not in r.get("drift_categories", []), \
                f"WARN category '{wc}' also in BLOCK categories!"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Field mismatch detection (using custom fixture manipulation via API)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFieldMismatchDetection:
    """Programmatic tests for field mismatch detection."""

    def test_provider_namespace_mismatch_blocks(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_drift import detect_drift_layer2
        import yaml

        pool = yaml.safe_load((REPO / "scripts" / "model_pool.yaml").read_text())
        nmc = yaml.safe_load((REPO / "scripts" / "node_model_capability.yaml").read_text())

        # Load valid 21bao fixture but change provider_namespace on first model
        fixture = json.loads((FIXT_DIR / "worker_attest_21bao.json").read_text())
        fixture["model_aliases"][0]["provider_namespace"] = "wrong-namespace"

        r = detect_drift_layer2(pool=pool, nmc=nmc, fixture_path=None)
        # Call with fixture passed directly
        from model_pool_drift import _load_fixture
        # We need to pass fixture in. Since detect_drift_layer2 loads from file,
        # let's use a different approach - save to temp and compare
        import tempfile
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(fixture, tf)
        tf.close()
        try:
            r = detect_drift_layer2(fixture_path=Path(tf.name), pool=pool, nmc=nmc)
            assert _has_category(r, "worker_provider_namespace_mismatch"), \
                f"Expected provider_namespace mismatch, got cats={r['drift_categories']}"
            assert _block_count(r) >= 1
        finally:
            Path(tf.name).unlink()

    def test_credential_status_mismatch_warns(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_drift import detect_drift_layer2
        import yaml, tempfile

        pool = yaml.safe_load((REPO / "scripts" / "model_pool.yaml").read_text())
        nmc = yaml.safe_load((REPO / "scripts" / "node_model_capability.yaml").read_text())
        fixture = json.loads((FIXT_DIR / "worker_attest_21bao.json").read_text())
        fixture["model_aliases"][0]["credential_status"] = "missing"

        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(fixture, tf)
        tf.close()
        try:
            r = detect_drift_layer2(fixture_path=Path(tf.name), pool=pool, nmc=nmc)
            assert _has_category(r, "worker_credential_status_mismatch"), \
                f"Expected credential_status mismatch, got cats={r['warn_categories']}"
        finally:
            Path(tf.name).unlink()

    def test_endpoint_ref_mismatch_warns(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_drift import detect_drift_layer2
        import yaml, tempfile

        pool = yaml.safe_load((REPO / "scripts" / "model_pool.yaml").read_text())
        nmc = yaml.safe_load((REPO / "scripts" / "node_model_capability.yaml").read_text())
        fixture = json.loads((FIXT_DIR / "worker_attest_21bao.json").read_text())
        fixture["model_aliases"][0]["endpoint_ref"] = "not_required"

        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(fixture, tf)
        tf.close()
        try:
            r = detect_drift_layer2(fixture_path=Path(tf.name), pool=pool, nmc=nmc)
            assert _has_category(r, "worker_endpoint_ref_mismatch"), \
                f"Expected endpoint_ref mismatch, got cats={r['warn_categories']}"
        finally:
            Path(tf.name).unlink()

    def test_lifecycle_status_mismatch_blocks(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_drift import detect_drift_layer2
        import yaml, tempfile

        pool = yaml.safe_load((REPO / "scripts" / "model_pool.yaml").read_text())
        nmc = yaml.safe_load((REPO / "scripts" / "node_model_capability.yaml").read_text())
        fixture = json.loads((FIXT_DIR / "worker_attest_21bao.json").read_text())
        # Change lifecycle_status from operator_requested to disabled
        fixture["model_aliases"][0]["lifecycle_status"] = "disabled"

        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(fixture, tf)
        tf.close()
        try:
            r = detect_drift_layer2(fixture_path=Path(tf.name), pool=pool, nmc=nmc)
            assert _has_category(r, "worker_lifecycle_status_mismatch"), \
                f"Expected lifecycle_status mismatch, got cats={r['drift_categories']}"
            assert _block_count(r) >= 1, "Lifecycle status mismatch must BLOCK"
        finally:
            Path(tf.name).unlink()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. No SSH / no subprocess / no os.environ
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoExternalAccess:
    """Drift Layer 2 must be purely local/fixture-based."""

    def test_no_subprocess_in_drift_module(self):
        import ast
        with open(SCRIPT, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "subprocess" != alias.name.split(".")[0], \
                        f"subprocess imported: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top != "subprocess", f"subprocess imported from: {node.module}"

    def test_no_ssh_libraries(self):
        import ast
        forbidden = {"paramiko", "fabric", "socket"}
        with open(SCRIPT, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, \
                        f"SSH library found: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top not in forbidden, \
                    f"SSH library found: {node.module}"

    def test_no_os_environ(self):
        import ast
        with open(SCRIPT, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "") == "os":
                    for alias in node.names:
                        assert alias.name not in ("environ", "getenv", "getenvb"), \
                            f"os.{alias.name} imported"
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    assert node.attr not in ("environ", "getenv"), \
                        f"os.{node.attr} accessed"

    def test_no_http_libraries(self):
        import ast
        forbidden = {"requests", "urllib", "urllib3"}
        with open(SCRIPT, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, \
                        f"HTTP library found: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top not in forbidden, \
                    f"HTTP library found: {node.module}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Secret/URL value redaction in Layer 2 output
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecretSafeOutput:
    """Layer 2 output must not contain leaked secret or URL values."""

    def test_valid_output_no_secret_url(self):
        r = _run_layer2("--node", "21bao")
        output = json.dumps(r)
        assert "http://" not in output, "URL leaked"
        assert "https://" not in output, "URL leaked"
        assert "***" not in output, "Secret leaked"

    def test_error_output_no_secret_url(self):
        """Error output for invalid fixtures should not leak values."""
        for fix in ["worker_attest_secret_leak.json", "worker_attest_url_leak.json"]:
            r = _run_layer2("--fixture", str(FIXT_DIR / fix))
            output = json.dumps(r)
            assert "http://" not in output, f"URL leaked in {fix}"
            assert "https://" not in output, f"URL leaked in {fix}"
            assert "***" not in output, f"Secret leaked in {fix}"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Audit-safe output schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditSafeOutput:
    """Layer 2 output should only contain expected safe fields."""

    BASE_FIELDS = {"drift_detected", "drift_count", "warn_count",
                   "drift_categories", "warn_categories", "details",
                   "warnings", "layer", "node", "fixture_path",
                   "model_count", "blocked_reason"}

    def test_valid_output_fields(self):
        r = _run_layer2("--node", "21bao")
        for key in r:
            assert key in self.BASE_FIELDS, f"Unexpected field: {key}"

    def test_error_output_fields(self):
        r = _run_layer2("--node", "nonexistent")
        for key in r:
            assert key in self.BASE_FIELDS, f"Unexpected field: {key}"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. BIDI scan
# ═══════════════════════════════════════════════════════════════════════════════

class TestBidiControl:
    """Source files must not contain hidden bidi control characters."""

    FILES = [
        REPO / "scripts" / "model_pool_drift.py",
        REPO / "tests" / "test_model_pool_drift_worker_attest.py",
    ]
    BIDI_CHARS = set(chr(c) for c in range(0x202A, 0x202F)) | \
                 set(chr(c) for c in range(0x2066, 0x206A)) | \
                 {"\u200E", "\u200F"}

    def test_no_bidi_in_drift(self):
        src = self.FILES[0].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, f"BIDI at offset {i}: U+{ord(ch):04X}"

    def test_no_bidi_in_test(self):
        src = self.FILES[1].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, f"BIDI at offset {i}: U+{ord(ch):04X}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Layer 1 still works
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer1StillWorks:
    """Layer 1 detection must still function after Layer 2 additions."""

    def test_layer1_self_check(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-check"],
            capture_output=True, text=True, timeout=15,
        )
        d = json.loads(result.stdout)
        assert d["status"] == "PASS"

    def test_layer1_detect(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "detect"],
            capture_output=True, text=True, timeout=15,
        )
        d = json.loads(result.stdout)
        assert d["layer"] == 1
        assert d["drift_detected"] is False
        assert d["warn_count"] == 48
