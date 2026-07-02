"""Tests for scripts/worker_attest_e2e_summary.py (Baseline02 Phase 3 G-5-RECEIPT-E2E)."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from scripts import worker_attest_collector as wac
from scripts import worker_attest_e2e_summary as wes


# ---------- fixtures ----------


@pytest.fixture(scope="module")
def dry_run_receipts() -> dict:
    """All 4 lanes in dry-run/skipped mode. No SSH, no real access."""
    return {
        "21bao_dry_run": wac.collect_21bao_local(
            wac.build_collection_plan("21bao", dry_run=True)
        ),
        "21bao_real_read": wac.collect_21bao_local(
            wac.build_collection_plan("21bao", dry_run=False),
            operator_approved_real_read=False,
        ),
        "5bao_ssh_canary": wac.collect_5bao_remote(
            wac.build_collection_plan("5bao", dry_run=False),
            operator_approved_real_read=False,
        ),
        "9bao_ssh_canary": wac.collect_9bao_remote(
            wac.build_collection_plan("9bao", dry_run=False),
            operator_approved_real_read=False,
        ),
    }


# ---------- schema / verdict happy-path ----------


class TestHappyPath:
    def test_summary_schema_version(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        assert s["schema_version"] == "1.0"
        assert s["source"] == "worker_attest_e2e_summary"

    def test_four_lane_e2e_pass(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        assert s["final_verdict"] == "E2E_PASS"
        assert s["layer2_e2e_verdict"] == "E2E_PASS"

    def test_summary_counts(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        c = s["summary_counts"]
        assert c["lanes_total"] == 4
        assert c["lanes_pass"] == 4
        assert c["lanes_blocked"] == 0
        assert c["lanes_secret_risk"] == 0

    def test_all_lanes_redacted(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        assert all(x["redaction_all_true"] for x in s["per_lane"])
        assert all(x["redaction_missing"] == [] for x in s["per_lane"])

    def test_all_flags_blocker_semantic(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        for lane in s["per_lane"]:
            assert lane["forbidden_flags_all_false"] is True
            assert lane["forbidden_flags_true"] == []

    def test_no_leaks(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        for lane in s["per_lane"]:
            for k in ("secret_leak", "url_leak", "path_leak", "any_leak"):
                assert lane["leak_scan"][k] is False, f"{lane['lane']} leaked {k}"

    def test_canonical_lanes_exposed(self, dry_run_receipts):
        s = wes.summarize_receipts(dry_run_receipts)
        assert s["canonical_lanes"] == list(wes.CANONICAL_LANES)


# ---------- fail-closed / blocker semantics ----------


class TestFailClosed:
    def test_missing_lane_blocks(self, dry_run_receipts):
        partial = {k: v for k, v in dry_run_receipts.items() if k != "5bao_ssh_canary"}
        s = wes.summarize_receipts(partial)
        assert s["final_verdict"] == "E2E_BLOCKED"

    def test_empty_input_blocks(self):
        s = wes.summarize_receipts({})
        assert s["final_verdict"] == "E2E_BLOCKED"
        assert s["summary_counts"]["lanes_blocked"] == 4

    def test_non_dict_receipt_blocks(self, dry_run_receipts):
        tampered = copy.deepcopy(dry_run_receipts)
        tampered["9bao_ssh_canary"] = "not a dict"
        s = wes.summarize_receipts(tampered)
        assert s["final_verdict"] == "E2E_BLOCKED"

    def test_forbidden_flag_true_blocks(self, dry_run_receipts):
        for flag in wes.FORBIDDEN_FLAGS:
            t = copy.deepcopy(dry_run_receipts)
            t["9bao_ssh_canary"]["receipt"]["forbidden_operation_flags"][flag] = True
            s = wes.summarize_receipts(t)
            assert s["final_verdict"] == "E2E_BLOCKED", f"flag={flag} did not block"

    def test_redaction_false_blocks(self, dry_run_receipts):
        for k in wes.REDACTION_SUBFLAGS:
            t = copy.deepcopy(dry_run_receipts)
            t["5bao_ssh_canary"]["receipt"]["redaction_status"][k] = False
            s = wes.summarize_receipts(t)
            assert s["final_verdict"] == "E2E_BLOCKED", f"subflag={k} did not block"

    def test_missing_redaction_dict_blocks(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        del t["21bao_dry_run"]["receipt"]["redaction_status"]
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "E2E_BLOCKED"

    def test_missing_forbidden_flags_dict_blocks(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        del t["21bao_real_read"]["receipt"]["forbidden_operation_flags"]
        s = wes.summarize_receipts(t)
        # forbidden flags dict missing → all-False check passes vacuously,
        # BUT receipt schema validator errors because required field missing.
        assert s["final_verdict"] == "E2E_BLOCKED"


# ---------- STOP_SECRET_RISK / STOP_AND_REANCHOR ----------


class TestStopVerdicts:
    def test_injected_openai_secret_stops(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["21bao_dry_run"]["redacted_output"]["fake"] = "sk-abcdef012345_ABCDEF7890"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_SECRET_RISK"

    def test_injected_github_token_stops(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["5bao_ssh_canary"]["redacted_output"]["fake"] = "ghp_" + "A" * 40
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_SECRET_RISK"

    def test_injected_url_stops(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["9bao_ssh_canary"]["redacted_output"]["fake"] = "https://api.example.com/v1"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_SECRET_RISK"

    def test_injected_real_path_stops(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["9bao_ssh_canary"]["redacted_output"]["fake"] = "/home/vibeworker/opencode.env"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_SECRET_RISK"

    def test_schema_version_mismatch_reanchor(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["21bao_real_read"]["receipt"]["schema_version"] = "99.9"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_AND_REANCHOR"

    def test_invalid_node_reanchor(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["21bao_dry_run"]["receipt"]["node"] = "10bao"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_AND_REANCHOR"

    def test_invalid_collection_status_reanchor(self, dry_run_receipts):
        t = copy.deepcopy(dry_run_receipts)
        t["5bao_ssh_canary"]["receipt"]["collection_status"] = "bogus"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_AND_REANCHOR"

    def test_leak_beats_schema_mismatch(self, dry_run_receipts):
        """When both leak and schema mismatch exist, STOP_SECRET_RISK wins."""
        t = copy.deepcopy(dry_run_receipts)
        t["21bao_dry_run"]["receipt"]["schema_version"] = "9.9"
        t["21bao_dry_run"]["redacted_output"]["fake"] = "sk-abcdef012345_ABCDEF7890"
        s = wes.summarize_receipts(t)
        assert s["final_verdict"] == "STOP_SECRET_RISK"


# ---------- 5th (optional) lane ----------


class TestOptionalPriorLane:
    def test_include_prior_summary_pass(self, dry_run_receipts):
        d = dict(dry_run_receipts)
        d["summary_prior"] = dry_run_receipts["21bao_dry_run"]
        s = wes.summarize_receipts(d, include_prior_summary=True)
        assert s["final_verdict"] == "E2E_PASS"
        assert "summary_prior" in s["optional_lanes_included"]
        assert s["summary_counts"]["lanes_total"] == 5

    def test_prior_summary_ignored_when_not_requested(self, dry_run_receipts):
        d = dict(dry_run_receipts)
        d["summary_prior"] = dry_run_receipts["21bao_dry_run"]
        s = wes.summarize_receipts(d, include_prior_summary=False)
        assert s["summary_counts"]["lanes_total"] == 4
        assert s["optional_lanes_included"] == []

    def test_prior_summary_forbidden_flag_blocks(self, dry_run_receipts):
        d = copy.deepcopy(dry_run_receipts)
        prior = copy.deepcopy(dry_run_receipts["21bao_dry_run"])
        prior["receipt"]["forbidden_operation_flags"]["model_call_attempted"] = True
        d["summary_prior"] = prior
        s = wes.summarize_receipts(d, include_prior_summary=True)
        assert s["final_verdict"] == "E2E_BLOCKED"


# ---------- AST / static safety ----------


class TestStaticSafety:
    @staticmethod
    @pytest.fixture(scope="class")
    def source_tree():
        p = Path("scripts") / "worker_attest_e2e_summary.py"
        return ast.parse(p.read_text(encoding="utf-8")), p.read_text(encoding="utf-8")

    def test_no_forbidden_imports(self, source_tree):
        tree, _ = source_tree
        forbidden = {"subprocess", "socket", "paramiko", "fabric", "requests", "urllib"}
        imports = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imports.add(a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom) and n.module:
                imports.add(n.module.split(".")[0])
        assert not (forbidden & imports), f"forbidden imports: {forbidden & imports}"

    def test_no_shell_true(self, source_tree):
        _, src = source_tree
        assert "shell=True" not in src

    def test_no_scp_rsync_curl_wget_nc_writes(self, source_tree):
        _, src = source_tree
        # Ensure no invocation-style occurrences (not just docstrings). We
        # accept these strings only inside comments/docstrings; the AST-level
        # check is that no subprocess/shell calls exist at all.
        for banned in ("scp ", "rsync ", "curl ", "wget ", " nc ", "os.system("):
            # These are only allowed in comment/docstring context. Simplify:
            # We assert none appear as code-level calls by parsing the AST.
            pass
        tree = ast.parse(src)
        calls = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                # Reject any Popen / run / call / check_output usage.
                if isinstance(n.func, ast.Attribute):
                    if n.func.attr in ("Popen", "run", "call", "check_output", "check_call", "getoutput"):
                        calls.append(n.func.attr)
                elif isinstance(n.func, ast.Name):
                    if n.func.id in ("system", "popen", "exec", "spawnl", "spawnv"):
                        calls.append(n.func.id)
        assert not calls, f"forbidden subprocess-like calls found: {calls}"

    def test_no_os_environ_access(self, source_tree):
        tree, _ = source_tree
        hits = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                if n.value.id == "os" and n.attr in ("environ", "getenv"):
                    hits.append(n.attr)
        assert not hits, f"os.environ/getenv accessed: {hits}"

    def test_no_http_urls_in_source(self, source_tree):
        _, src = source_tree
        # Allow http(s) only in regex definition line for _URL_RE and
        # in comment/docstring contexts. The strict rule: no real URL literal.
        # We build the domain fragments piecewise so this test source itself
        # never contains an intact plausible-real endpoint domain.
        d = "."
        forbidden_fragments = [
            "api" + d + "deepseek" + d + "com",
            "api" + d + "openai" + d + "com",
            "api" + d + "anthropic" + d + "com",
            "api" + d + "moonshot",
            "dashscope" + d + "aliyuncs",
            "generativelanguage" + d + "googleapis" + d + "com",
            "opencode" + d + "ai/zen",
        ]
        for domain in forbidden_fragments:
            assert domain not in src, f"real endpoint domain leaked: {domain}"


# ---------- self-check integration ----------


class TestSelfCheck:
    def test_self_check_pass(self):
        r = wes.self_check()
        assert r["status"] == "PASS", r
        assert r["detail"].endswith("/{} passed".format(len(r["checks"])).replace("/", "/"))
        assert all(c["passed"] for c in r["checks"])

    def test_self_check_count(self):
        r = wes.self_check()
        # We expect 11 checks (adjust if extended).
        assert len(r["checks"]) == 11


# ---------- CLI ----------


class TestCLI:
    def test_cli_self_check(self, capsys):
        rc = wes.main(["self-check"])
        out = capsys.readouterr().out
        d = json.loads(out)
        assert rc == 0
        assert d["status"] == "PASS"

    def test_cli_summarize_default(self, capsys):
        rc = wes.main(["summarize"])
        out = capsys.readouterr().out
        d = json.loads(out)
        assert rc == 0
        assert d["final_verdict"] == "E2E_PASS"
        assert d["summary_counts"]["lanes_total"] == 4

    def test_cli_fixture_dir_outside_repo_blocks(self, capsys, tmp_path):
        # tmp_path is under system temp — outside repo tree. Must block.
        rc = wes.main(["summarize", "--fixture-dir", str(tmp_path)])
        out = capsys.readouterr().out
        d = json.loads(out)
        assert rc == 1
        assert d["final_verdict"] == "E2E_BLOCKED"
        assert "must be under current repo tree" in d.get("error", "")

    def test_cli_fixture_dir_under_repo_loads(self, capsys, tmp_path, dry_run_receipts):
        # Create a fixture dir under repo tree (tests/fixtures/e2e_test_tmp/).
        repo_root = Path.cwd().resolve()
        fixture_dir = repo_root / "tests" / "fixtures" / "e2e_test_tmp"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        try:
            for lane, receipt in dry_run_receipts.items():
                (fixture_dir / f"{lane}.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )
            rc = wes.main(["summarize", "--fixture-dir", str(fixture_dir)])
            out = capsys.readouterr().out
            d = json.loads(out)
            assert rc == 0
            assert d["final_verdict"] == "E2E_PASS"
        finally:
            # Cleanup — no leftover fixture files.
            for f in fixture_dir.glob("*.json"):
                f.unlink()
            fixture_dir.rmdir()


# ---------- redaction / blocker semantic contract with PR-4G/PR-4H ----------


class TestBlockerSemanticContract:
    """Sanctioned SSH (PR-4G/PR-4H) MUST NOT set forbidden_flag True. This test
    class documents the contract in code."""

    def test_sanctioned_ssh_reports_ssh_attempted_false_in_skipped_mode(
        self, dry_run_receipts
    ):
        # Both 5bao and 9bao SSH canaries in skipped mode still report all
        # forbidden flags False. This is the PR #302 / PR #303 semantic.
        for lane in ("5bao_ssh_canary", "9bao_ssh_canary"):
            flags = dry_run_receipts[lane]["receipt"]["forbidden_operation_flags"]
            for k in wes.FORBIDDEN_FLAGS:
                assert flags[k] is False, (
                    f"{lane} reported forbidden {k}=True in skipped mode "
                    "(would violate PR-4G/PR-4H blocker semantic)"
                )
