#!/usr/bin/env python3
"""I23 Runtime Reliability — targeted tests.

Verifies:
1. ARCH-002: Worker health_status is documented in self-check
2. WRKR-002: Worker failover readiness check returns structured output
3. DSP-003: Fallback policy consistency check
4. GIT-001: PR base lag detection works
5. WIN-003: MSYS path artifact detection
6. RPT-001: Report field schema check
7. RPT-002: Enhanced secret check with false-positive classification
8. Route-all unchanged (9 roles)
9. Model pool unchanged
10. Secret safety
"""

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ═══════════════════════════════════════════════════════════════════
# ARCH-002: Worker Health Status
# ═══════════════════════════════════════════════════════════════════

class TestWorkerHealthStatus:
    """ARCH-002: Worker health_status in architecture self-check."""

    def test_worker_health_status_in_self_check(self):
        """self_check() must include worker_health_status check."""
        from vibe_architecture_contract import self_check
        result = self_check()
        check_names = [c["name"] for c in result["checks"]]
        assert "worker_health_status" in check_names, \
            f"Missing worker_health_status check: {check_names}"

    def test_worker_registry_has_health_field(self):
        """All workers must have a non-empty health_status field."""
        from vibe_worker_registry import WorkerRegistry
        reg = WorkerRegistry()
        for wid, w in reg.workers.items():
            assert hasattr(w, "health_status"), \
                f"{wid} missing health_status"
            # health_status can be UNKNOWN but not empty
            assert w.health_status != "", \
                f"{wid} has empty health_status"


# ═══════════════════════════════════════════════════════════════════
# WRKR-002: Worker Failover Readiness
# ═══════════════════════════════════════════════════════════════════

class TestWorkerFailoverReadiness:
    """WRKR-002: Worker failover readiness assessment."""

    def test_module_importable(self):
        from vibe_runtime_reliability import check_failover_readiness
        assert callable(check_failover_readiness)

    def test_failover_check_returns_expected_fields(self):
        from vibe_runtime_reliability import check_failover_readiness
        result = check_failover_readiness()
        assert "passed" in result
        assert "check_type" in result
        assert result["check_type"] == "wrkr-002"
        assert "debian_online_count" in result
        assert "debian_offline_count" in result
        assert isinstance(result["debian_online_count"], int)
        assert isinstance(result["debian_offline_count"], int)
        assert isinstance(result["findings"], list)

    def test_failover_check_no_error(self):
        """Should not crash even when workers are OFFLINE."""
        from vibe_runtime_reliability import check_failover_readiness
        result = check_failover_readiness()
        assert "error" not in result or result.get("error") is None


# ═══════════════════════════════════════════════════════════════════
# DSP-003: Fallback Policy Enforcement
# ═══════════════════════════════════════════════════════════════════

class TestFallbackPolicy:
    """DSP-003: Fallback policy consistency check."""

    def test_fallback_check_importable(self):
        from vibe_runtime_reliability import check_fallback_policy
        assert callable(check_fallback_policy)

    def test_fallback_check_returns_expected_fields(self):
        from vibe_runtime_reliability import check_fallback_policy
        result = check_fallback_policy()
        assert "passed" in result
        assert result["check_type"] == "dsp-003"
        assert "total_models_checked" in result
        assert "models_with_valid_fallback" in result
        assert isinstance(result["total_models_checked"], int)
        assert isinstance(result["models_with_valid_fallback"], int)

    def test_fallback_check_covers_entire_pool(self):
        from vibe_runtime_reliability import check_fallback_policy
        result = check_fallback_policy()
        assert result["total_models_checked"] >= 40, \
            f"Expected 40+ models, got {result['total_models_checked']}"


# ═══════════════════════════════════════════════════════════════════
# GIT-001: PR Base Lag Detection
# ═══════════════════════════════════════════════════════════════════

class TestPrBaseLagDetection:
    """GIT-001: PR base ref lag detection."""

    def test_pr_base_lag_importable(self):
        from vibe_runtime_reliability import check_pr_base_lag
        assert callable(check_pr_base_lag)

    def test_pr_base_lag_returns_fields(self):
        from vibe_runtime_reliability import check_pr_base_lag
        result = check_pr_base_lag()
        assert "passed" in result
        assert "findings" in result
        assert "branch" in result["findings"]
        assert "behind_count" in result["findings"]
        assert isinstance(result["findings"]["behind_count"], int)


# ═══════════════════════════════════════════════════════════════════
# WIN-003: MSYS Path Artifact Detection
# ═══════════════════════════════════════════════════════════════════

class TestMsysPathDetection:
    """WIN-003: MSYS/POSIX path artifact detection."""

    def test_msys_check_importable(self):
        from vibe_runtime_reliability import check_msys_path_artifacts
        assert callable(check_msys_path_artifacts)

    def test_msys_check_returns_fields(self):
        from vibe_runtime_reliability import check_msys_path_artifacts
        result = check_msys_path_artifacts()
        assert "passed" in result
        assert result["check_type"] == "win-003"
        assert "files_checked" in result
        assert "issues_count" in result
        assert isinstance(result["issues_count"], int)

    def test_msys_check_identifies_c_users_artifact(self):
        """Detection of C:\\c\\Users pattern should work."""
        from vibe_runtime_reliability import check_msys_path_artifacts
        import tempfile
        # Write literal content using embedded raw string (avoid \U escape issue)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         delete=False, dir=SCRIPTS_DIR) as f:
            f.write("# test with MSYS artifact\n")
            f.write("path = \"C:")
            f.write("\\")  # single backslash
            f.write("c")
            f.write("\\")  # single backslash
            f.write("Users")
            f.write("\\")  # single backslash
            f.write("KK")
            f.write("\\")  # single backslash
            f.write("test\"\n")
            tmppath = f.name
        try:
            result = check_msys_path_artifacts([tmppath])
            assert result["issues_count"] >= 1, \
                f"Should detect MSYS artifact, got {result}"
            error_issues = [i for i in result["issues"]
                           if i.get("severity") == "error"]
            assert len(error_issues) >= 1, \
                f"Should flag error for C:\\\\c\\\\Users pattern"
        finally:
            if os.path.exists(tmppath):
                os.unlink(tmppath)


# ═══════════════════════════════════════════════════════════════════
# RPT-001: Report Schema Check
# ═══════════════════════════════════════════════════════════════════

class TestReportSchemaCheck:
    """RPT-001: Report field presence consistency."""

    def test_report_check_importable(self):
        from vibe_runtime_reliability import check_report_schema
        assert callable(check_report_schema)

    def test_report_check_returns_fields(self):
        from vibe_runtime_reliability import check_report_schema
        result = check_report_schema()
        assert "passed" in result
        assert result["check_type"] == "rpt-001"
        assert "reports_scanned" in result
        assert "total_missing_fields" in result
        assert isinstance(result["reports_scanned"], int)


# ═══════════════════════════════════════════════════════════════════
# RPT-002: Enhanced Secret Check
# ═══════════════════════════════════════════════════════════════════

class TestEnhancedSecretCheck:
    """RPT-002: Enhanced secret detection with false-positive classification."""

    def test_secret_check_importable(self):
        from vibe_runtime_reliability import enhanced_secret_check
        assert callable(enhanced_secret_check)

    def test_secret_check_returns_fields(self):
        from vibe_runtime_reliability import enhanced_secret_check
        result = enhanced_secret_check([])  # Empty file list, no crash
        assert "passed" in result
        assert result["check_type"] == "rpt-002"
        assert "false_positives" in result
        assert "real_concerns" in result
        assert isinstance(result["false_positives"], int)
        assert isinstance(result["real_concerns"], int)

    def test_secret_check_classifies_regex_pattern_fp(self):
        """Regex pattern definitions must be classified as false positives."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         delete=False) as f:
            f.write("# Contains regex pattern definition\n")
            f.write("SECRET_PATTERN=*** r'sk-test123456789' \n")
            f.write("PATTERN=*** r'ghp_test' \n")
            tmppath = f.name
        try:
            from vibe_runtime_reliability import enhanced_secret_check
            result = enhanced_secret_check([tmppath])
            # All matches should be classified as false positives
            if result["total_matches"] > 0:
                assert result["false_positives"] == result["total_matches"], \
                    f"Regex patterns should be FP: {result}"
        finally:
            os.unlink(tmppath)

    def test_secret_check_classifies_placeholder_fp(self):
        """Placeholder values like AKIAIO...MPLE must be FP."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         delete=False) as f:
            f.write("# Contains placeholder\n")
            f.write("key = \"AKIAIO...MPLE\"\n")
            tmppath = f.name
        try:
            from vibe_runtime_reliability import enhanced_secret_check
            result = enhanced_secret_check([tmppath])
            # The short placeholder should be classified as FP
            for match in result.get("matches", []):
                if "AKIA" in match.get("pattern", ""):
                    assert match["is_false_positive"], \
                        f"Placeholder should be FP: {match}"
        finally:
            os.unlink(tmppath)


# ═══════════════════════════════════════════════════════════════════
# Module-level self-check
# ═══════════════════════════════════════════════════════════════════

class TestReliabilityModuleSelfCheck:
    """The vibe_runtime_reliability module --self-check runs cleanly."""

    def test_self_check_runs_without_error(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_runtime_reliability.py",
             "--self-check", "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, \
            f"self-check failed: {result.stderr[:200]}"
        data = json.loads(result.stdout)
        # Should have 7 check types
        assert data["total"] == 7, \
            f"Expected 7 checks, got {data['total']}"
        assert isinstance(data["passed_count"], int)


# ═══════════════════════════════════════════════════════════════════
# No-Regression Checks
# ═══════════════════════════════════════════════════════════════════

class TestNoRegression:
    """I23 must not change route-all, model_pool, or introduce secrets."""

    def test_route_all_nine_roles(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_model_routing_policy.py",
             "--json", "route-all"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"route-all failed: {result.stderr}"
        data = json.loads(result.stdout)
        roles = {k: v for k, v in data.items() if not k.startswith("_")}
        assert len(roles) == 9, f"Expected 9 roles, got {len(roles)}"
        expected_roles = {"orchestrator", "explorer", "planner", "implementer",
                          "tester-a", "tester-b", "reviewer-a", "reviewer-b",
                          "git-integrator"}
        assert set(roles.keys()) == expected_roles

    def test_model_pool_unchanged(self):
        result = subprocess.run(
            [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["passed"], "model_pool self-check failed"
        assert data["passed_count"] >= 129

    def test_architecture_contract_self_check(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_architecture_contract.py",
             "--self-check", "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, \
            f"arch contract self-check failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["passed"], "Architecture contract checks failed"
        # Should now have 10 checks (9 original + worker_health_status)
        assert len(data["checks"]) >= 9

    def test_no_secrets_in_i23_changes(self):
        """No real secrets in I23 modified files."""
        from vibe_runtime_reliability import enhanced_secret_check
        files_to_check = [
            os.path.join(REPO_ROOT, f)
            for f in [
                "scripts/vibe_runtime_reliability.py",
                "scripts/vibe_architecture_contract.py",
            ]
        ]
        result = enhanced_secret_check(files_to_check)
        assert result["total_matches"] == 0 or result["real_concerns"] == 0, \
            f"Secret concerns found in I23 files: {result['matches']}"
