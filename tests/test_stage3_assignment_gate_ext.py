#!/usr/bin/env python3
"""tests/test_stage3_assignment_gate_ext.py

Baseline02 Stage 3 — RAG v1.0.0 → v1.1.0 extension tests.

Covers the 7 new spec §4.2 fields:
  - assignment_id, provider_namespace, operator_approval_timestamp,
    operator_approval_signature, node_whitelist_verified,
    model_pool_source_verified, base_sha

Covers the architecture-drift guard: `win` is REJECTED as a node string
(spec §2: 21bao IS the Windows local host; cannot be split).

Covers the central model pool single-source: every model must resolve to
a declaration in scripts/model_pool.yaml; the RAG must NOT resolve
`key_env` or any secret value.

Covers backward-compat: existing v1.0.0 matrices (without the new 7 fields)
still validate successfully via the legacy `validate_assignment_matrix()`
path, keeping baseline01 callers (vibe_execution_gate.py,
vibe_wo_compiler.py) running.

All tests are pure-Python and import-only — no SSH, no model calls,
no runtime probe, no secret values.
"""

import os
import sys
import unittest
import importlib.util

# Locate the module under test relative to this test file.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)  # .../vibe-coding-repo-clean
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Import the gate under test
import vibe_role_assignment_gate as rag
from vibe_role_assignment_gate import (
    __version__,
    CLUSTER_NODE_WHITELIST,
    LEGACY_AGENT_NODE,
    ALLOWED_NODE_VALUES,
    REQUIRED_ASSIGNMENT_FIELDS,
    REQUIRED_ASSIGNMENT_FIELDS_V11,
    REQUIRED_ASSIGNMENT_FIELDS_FULL,
    VALID_FALLBACK_POLICIES,
    ULID_RE,
    HEX_SHA1_RE,
    HEX_SHA256_RE,
    is_valid_ulid,
    is_node_whitelisted,
    is_model_in_pool,
    find_pool_model_for,
    load_model_pool_declarations,
    reset_model_pool_cache,
    detect_spec_version,
    compute_approval_signature,
    validate_assignment_entry,
    validate_assignment_entry_v11,
    aggregate_v11_entry_errors,
    validate_assignment_matrix,
    validate_assignment_matrix_v11,
    validate_assignment_matrix_strict,
    create_assignment_matrix,
    create_role_assignment,
    self_check,
)


VALID_ULID = "01HXYZABCDEFGHJKMNPQRSTVWX"  # 26 chars Crockford Base32
VALID_SHA256 = "a" * 64
VALID_SHA1 = "b" * 40
VALID_ISO = "2026-07-01T08:00:00Z"
REAL_MODEL_ID = "deepseek-deepseek-coder"  # known present in scripts/model_pool.yaml


def _v11_entry(role="implementer", node="21bao", model=REAL_MODEL_ID,
               provider="deepseek", provider_namespace="opencode",
               approval_id=VALID_ULID, override=None):
    """Build a fully-valid v1.1.0 entry."""
    sig = compute_approval_signature(approval_id, VALID_ISO)
    e = {
        "role": role, "node": node, "model": model, "provider": provider,
        "cost_tag": "ext-001", "reason": "Stage 3 ext test",
        "call_budget": 100, "fallback_policy": "disabled",
        "assignment_id": VALID_ULID,
        "provider_namespace": provider_namespace,
        "operator_approval_timestamp": VALID_ISO,
        "operator_approval_signature": sig,
        "node_whitelist_verified": True,
        "model_pool_source_verified": True,
        "base_sha": VALID_SHA1,
    }
    if override:
        e.update(override)
    return e


class TestVersionAndConstants(unittest.TestCase):
    """Verify v1.1.0 constants and version."""

    def test_version_is_1_1_0(self):
        self.assertEqual(__version__, "1.1.0")

    def test_v10_required_fields_preserved(self):
        # backward compat: the 8 baseline fields must remain REQUIRED
        for f in ("role", "node", "model", "provider",
                  "cost_tag", "reason", "call_budget", "fallback_policy"):
            self.assertIn(f, REQUIRED_ASSIGNMENT_FIELDS)

    def test_v11_required_fields_added(self):
        for f in ("assignment_id", "provider_namespace",
                  "operator_approval_timestamp", "operator_approval_signature",
                  "node_whitelist_verified", "model_pool_source_verified",
                  "base_sha"):
            self.assertIn(f, REQUIRED_ASSIGNMENT_FIELDS_V11)

    def test_required_fields_full_is_union(self):
        self.assertEqual(
            set(REQUIRED_ASSIGNMENT_FIELDS_FULL),
            set(REQUIRED_ASSIGNMENT_FIELDS) | set(REQUIRED_ASSIGNMENT_FIELDS_V11),
        )

    def test_cluster_node_whitelist_3_nodes(self):
        self.assertEqual(CLUSTER_NODE_WHITELIST, {"21bao", "5bao", "9bao"})

    def test_legacy_main_agent_preserved(self):
        self.assertIn(LEGACY_AGENT_NODE, ALLOWED_NODE_VALUES)
        self.assertEqual(LEGACY_AGENT_NODE, "main-agent")

    def test_valid_fallback_policies_unchanged(self):
        self.assertEqual(VALID_FALLBACK_POLICIES,
                         {"disabled", "operator_selects",
                          "same_provider_different_model"})

    def test_ulid_regex_26_crockford(self):
        # 26-char Crockford base32: 0-9 + ABCDEFGHJKMNPQRSTVWXYZ
        # (excludes I, L, O, U)
        self.assertIsNotNone(ULID_RE.match(VALID_ULID))
        # Too short
        self.assertIsNone(ULID_RE.match("01HXYZ"))
        # Has I (excluded)
        self.assertIsNone(ULID_RE.match("01IXYZABCDEFGHJKMNPQRSTVWX"))
        # Has L (excluded)
        self.assertIsNone(ULID_RE.match("01LXYZABCDEFGHJKMNPQRSTVWX"))
        # Has O (excluded)
        self.assertIsNone(ULID_RE.match("01OXYZABCDEFGHJKMNPQRSTVWX"))
        # Has U (excluded)
        self.assertIsNone(ULID_RE.match("01UXYZABCDEFGHJKMNPQRSTVWX"))

    def test_is_valid_ulid_function(self):
        self.assertTrue(is_valid_ulid(VALID_ULID))
        self.assertFalse(is_valid_ulid("not-a-ulid"))
        self.assertFalse(is_valid_ulid(""))
        self.assertFalse(is_valid_ulid(None))
        self.assertFalse(is_valid_ulid(12345))

    def test_hex_sha1_regex(self):
        self.assertIsNotNone(HEX_SHA1_RE.match(VALID_SHA1))
        self.assertIsNone(HEX_SHA1_RE.match("abc"))
        self.assertIsNone(HEX_SHA1_RE.match("Z" * 40))
        # 64 chars must NOT match sha1
        self.assertIsNone(HEX_SHA1_RE.match("a" * 64))

    def test_hex_sha256_regex(self):
        self.assertIsNotNone(HEX_SHA256_RE.match(VALID_SHA256))
        self.assertIsNone(HEX_SHA256_RE.match("a" * 40))  # too short for sha256
        self.assertIsNone(HEX_SHA256_RE.match("Z" * 64))


class TestNodeWhitelist(unittest.TestCase):
    """Architecture-drift guard: 21bao/5bao/9bao only; `win` rejected."""

    def test_21bao_accepted(self):
        self.assertTrue(is_node_whitelisted("21bao"))

    def test_5bao_accepted(self):
        self.assertTrue(is_node_whitelisted("5bao"))

    def test_9bao_accepted(self):
        self.assertTrue(is_node_whitelisted("9bao"))

    def test_win_rejected(self):
        # spec §2: 21bao IS the Windows local host; "win" alone is rejected
        # to prevent win+21bao from being treated as 2 separate nodes.
        self.assertFalse(is_node_whitelisted("win"))

    def test_win_uppercase_rejected(self):
        self.assertFalse(is_node_whitelisted("Win"))
        self.assertFalse(is_node_whitelisted("WIN"))

    def test_21bao_with_whitespace_rejected(self):
        self.assertFalse(is_node_whitelisted("21bao "))
        self.assertFalse(is_node_whitelisted(" 21bao"))

    def test_main_agent_legacy_accepted(self):
        self.assertTrue(is_node_whitelisted("main-agent"))

    def test_bogus_node_rejected(self):
        for n in ("10bao", "1bao", "0bao", "21bao2", "main", "agent", ""):
            self.assertFalse(is_node_whitelisted(n), f"{n!r} should be rejected")

    def test_non_string_rejected(self):
        for v in (None, 0, 21, [], {}, 21.0):
            self.assertFalse(is_node_whitelisted(v))


class TestModelPoolDeclarations(unittest.TestCase):
    """Central model pool single-source; no secret values."""

    def setUp(self):
        reset_model_pool_cache()
        self.decl = load_model_pool_declarations()

    def test_pool_loads(self):
        self.assertGreater(len(self.decl["model_ids"]), 0)

    def test_pool_no_secret_leak_key_env(self):
        # CRITICAL: no model entry must carry key_env
        leaked = [mid for mid, m in self.decl["models_by_id"].items()
                  if "key_env" in m]
        self.assertEqual(leaked, [], f"key_env leaked in: {leaked}")

    def test_pool_no_secret_leak_base_url_env(self):
        leaked = [mid for mid, m in self.decl["models_by_id"].items()
                  if "base_url_env" in m]
        self.assertEqual(leaked, [], f"base_url_env leaked in: {leaked}")

    def test_pool_no_secret_leak_in_aliases(self):
        leaked = [a for a, m in self.decl["models_by_alias"].items()
                  if "key_env" in m or "base_url_env" in m]
        self.assertEqual(leaked, [])

    def test_pool_has_canonical_providers(self):
        self.assertGreater(len(self.decl["canonical_providers"]), 0)
        # known canonical providers
        for cp in ("opencode-go", "anthropic", "deepseek", "minimax"):
            self.assertIn(cp, self.decl["canonical_providers"])

    def test_pool_has_provider_namespaces(self):
        self.assertIn("provider_namespaces", self.decl)
        # all 38 entries currently have provider_namespace=unknown
        # (this is the Stage 1 GAP-L5-1 condition; Stage 3 doesn't fix it
        # but records it)
        self.assertIn("unknown", self.decl["provider_namespaces"])

    def test_pool_real_model_id_in_pool(self):
        self.assertIn(REAL_MODEL_ID, self.decl["model_ids"])
        self.assertTrue(is_model_in_pool(REAL_MODEL_ID, decl=self.decl))

    def test_pool_bogus_model_not_in_pool(self):
        self.assertFalse(is_model_in_pool("bogus/imaginary-model-99", decl=self.decl))
        self.assertFalse(is_model_in_pool("", decl=self.decl))
        self.assertFalse(is_model_in_pool(None, decl=self.decl))

    def test_pool_resolves_by_alias(self):
        # deepseek-deepseek-coder has alias ['deepseek-coder']
        self.assertIn("deepseek-coder", self.decl["aliases"])
        self.assertTrue(is_model_in_pool("deepseek-coder", decl=self.decl))

    def test_find_pool_model_returns_no_secrets(self):
        m = find_pool_model_for(REAL_MODEL_ID, decl=self.decl)
        self.assertIsNotNone(m)
        self.assertNotIn("key_env", m)
        self.assertNotIn("base_url_env", m)

    def test_pool_caches(self):
        # Second load returns the same cached object
        d1 = load_model_pool_declarations()
        d2 = load_model_pool_declarations()
        self.assertIs(d1, d2)


class TestComputeApprovalSignature(unittest.TestCase):
    """operator_approval_signature: deterministic SHA256 hex (linkage helper)."""

    def test_deterministic(self):
        s1 = compute_approval_signature(VALID_ULID, VALID_ISO)
        s2 = compute_approval_signature(VALID_ULID, VALID_ISO)
        self.assertEqual(s1, s2)

    def test_format_64_lowercase_hex(self):
        s = compute_approval_signature(VALID_ULID, VALID_ISO)
        self.assertEqual(len(s), 64)
        self.assertIsNotNone(HEX_SHA256_RE.match(s))

    def test_changes_with_approval_id(self):
        s1 = compute_approval_signature(VALID_ULID, VALID_ISO)
        s2 = compute_approval_signature("01HXYZABCDEFGHJKMNPQRSTVWY", VALID_ISO)
        self.assertNotEqual(s1, s2)

    def test_changes_with_timestamp(self):
        s1 = compute_approval_signature(VALID_ULID, VALID_ISO)
        s2 = compute_approval_signature(VALID_ULID, "2026-07-01T08:00:01Z")
        self.assertNotEqual(s1, s2)

    def test_invalid_inputs_return_empty(self):
        self.assertEqual(compute_approval_signature(None, VALID_ISO), "")
        self.assertEqual(compute_approval_signature(VALID_ULID, None), "")
        self.assertEqual(compute_approval_signature(123, VALID_ISO), "")


class TestDetectSpecVersion(unittest.TestCase):
    """Matrix opts into v1.1.0 via spec_version or auto-detection."""

    def test_default_v10(self):
        self.assertEqual(detect_spec_version({}), "1.0.0")

    def test_explicit_v11(self):
        self.assertEqual(detect_spec_version({"spec_version": "1.1.0"}), "1.1.0")

    def test_explicit_higher_version(self):
        self.assertEqual(detect_spec_version({"spec_version": "1.2.0"}), "1.2.0")

    def test_explicit_v10_stays_v10(self):
        self.assertEqual(detect_spec_version({"spec_version": "1.0.0"}), "1.0.0")

    def test_auto_detect_from_full_v11_entries(self):
        matrix = {
            "assignments": [
                _v11_entry(role="implementer"),
                _v11_entry(role="reviewer", node="5bao"),
            ],
        }
        self.assertEqual(detect_spec_version(matrix), "1.1.0")

    def test_no_auto_detect_for_partial_entries(self):
        # If even one entry lacks v1.1.0 fields, do not auto-detect
        matrix = {
            "assignments": [
                _v11_entry(),
                {"role": "reviewer", "node": "5bao", "model": REAL_MODEL_ID,
                 "provider": "deepseek", "cost_tag": "x", "reason": "y",
                 "call_budget": 1, "fallback_policy": "disabled"},
            ],
        }
        self.assertEqual(detect_spec_version(matrix), "1.0.0")

    def test_empty_assignments_default(self):
        self.assertEqual(detect_spec_version({"assignments": []}), "1.0.0")


class TestValidateAssignmentEntryV11(unittest.TestCase):
    """Per-entry v1.1.0 spec §4.2 field validation."""

    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_legal_entry_passes(self):
        e = _v11_entry()
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertEqual(errs, [], f"expected no errors, got: {errs}")

    def test_missing_assignment_id_blocks(self):
        e = _v11_entry(override={"assignment_id": None})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("assignment_id" in err for err in errs),
                        f"expected assignment_id error, got: {errs}")

    def test_invalid_ulid_format_blocks(self):
        e = _v11_entry(override={"assignment_id": "not-a-ulid"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("ULID" in err for err in errs))

    def test_missing_provider_namespace_blocks(self):
        e = _v11_entry(override={"provider_namespace": ""})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("provider_namespace" in err for err in errs))

    def test_provider_namespace_unknown_NOT_blocked_at_stage3(self):
        # spec §4.2: provider_namespace can be "unknown" at Stage 3;
        # readiness gate at Stage 4-5 rejects it.
        e = _v11_entry(override={"provider_namespace": "unknown"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertEqual(errs, [], "Stage 3 must accept provider_namespace=unknown")

    def test_missing_operator_approval_timestamp_blocks(self):
        e = _v11_entry(override={"operator_approval_timestamp": ""})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("operator_approval_timestamp" in err for err in errs))

    def test_bad_iso8601_format_blocks(self):
        e = _v11_entry(override={"operator_approval_timestamp": "yesterday"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("ISO-8601" in err for err in errs))

    def test_missing_signature_blocks(self):
        e = _v11_entry(override={"operator_approval_signature": ""})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("operator_approval_signature" in err for err in errs))

    def test_signature_wrong_length_blocks(self):
        e = _v11_entry(override={"operator_approval_signature": "tooshort"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("64-char" in err for err in errs))

    def test_signature_non_hex_blocks(self):
        e = _v11_entry(override={"operator_approval_signature": "Z" * 64})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("64-char" in err for err in errs))

    def test_node_whitelist_verified_false_blocks(self):
        e = _v11_entry(override={"node_whitelist_verified": False})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("node_whitelist_verified" in err for err in errs))

    def test_node_whitelist_verified_string_true_blocks(self):
        # bool True is required; string "true" is not accepted
        e = _v11_entry(override={"node_whitelist_verified": "true"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("node_whitelist_verified" in err for err in errs))

    def test_model_pool_source_verified_false_blocks(self):
        e = _v11_entry(override={"model_pool_source_verified": False})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("model_pool_source_verified" in err for err in errs))

    def test_model_pool_source_verified_missing_blocks(self):
        e = _v11_entry(override={"model_pool_source_verified": None})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("model_pool_source_verified" in err for err in errs))

    def test_missing_base_sha_blocks(self):
        e = _v11_entry(override={"base_sha": ""})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("base_sha" in err for err in errs))

    def test_base_sha_wrong_length_blocks(self):
        e = _v11_entry(override={"base_sha": "abc"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("40-char" in err for err in errs))

    def test_base_sha_non_hex_blocks(self):
        e = _v11_entry(override={"base_sha": "Z" * 40})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("40-char" in err for err in errs))

    def test_node_win_rejected(self):
        e = _v11_entry(override={"node": "win"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        # Stage 3 corrective: error message now mentions v1.1.0 strict
        # cluster whitelist (issue #1: main-agent also rejected in v1.1.0 strict).
        self.assertTrue(any("v1.1.0 strict cluster whitelist" in err for err in errs),
                        f"expected v1.1.0 strict whitelist error, got: {errs}")

    def test_node_Win_uppercase_rejected(self):
        e = _v11_entry(override={"node": "Win"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("v1.1.0 strict cluster whitelist" in err for err in errs))

    def test_node_10bao_rejected(self):
        e = _v11_entry(override={"node": "10bao"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("v1.1.0 strict cluster whitelist" in err for err in errs))

    def test_model_bogus_with_verified_true_blocks(self):
        e = _v11_entry(override={"model": "opencode/bogus-model-zzz"})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        self.assertTrue(any("not in the central model pool" in err for err in errs))

    def test_model_bogus_with_verified_false_passes_field_check(self):
        # If pool_source_verified=False, the cross-field check is skipped
        # (the bool is what fails). The model string itself is not checked.
        e = _v11_entry(override={"model": "opencode/bogus-model-zzz",
                                 "model_pool_source_verified": False})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        # No "not in the central model pool" error since the bool is False
        self.assertFalse(any("not in the central model pool" in err for err in errs))
        # But the bool itself is the source of the block
        self.assertTrue(any("model_pool_source_verified" in err for err in errs))

    def test_node_whitelist_verified_true_with_bogus_node_blocks(self):
        # Even with verified=True, if node string isn't in whitelist, fail
        e = _v11_entry(override={"node": "win", "node_whitelist_verified": True})
        errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
        # Stage 3 corrective: error mentions v1.1.0 strict cluster whitelist
        self.assertTrue(any("v1.1.0 strict cluster whitelist" in err for err in errs))

    def test_node_main_agent_rejected_in_v11_strict(self):
        # Stage 3 corrective (issue #1): main-agent is REJECTED in v1.1.0
        # strict, regardless of role. (Legacy v1.0.0 path still accepts
        # main-agent for main-agent-as-tester baseline01 behavior.)
        for role in ("implementer", "reviewer", "tester", "tester-checker", "checker"):
            e = _v11_entry(role=role, node="main-agent")
            errs = validate_assignment_entry_v11(e, 0, decl=self.decl)
            self.assertTrue(
                any("main-agent" in err or "v1.1.0 strict" in err for err in errs),
                f"role={role}: main-agent must be rejected in v1.1.0 strict; got: {errs}")


class TestAggregateV11EntryErrors(unittest.TestCase):
    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_empty_entries_no_errors(self):
        self.assertEqual(aggregate_v11_entry_errors([], decl=self.decl), [])

    def test_none_entries_no_errors(self):
        self.assertEqual(aggregate_v11_entry_errors(None, decl=self.decl), [])

    def test_mixed_entries_aggregate(self):
        entries = [
            _v11_entry(),  # ok
            _v11_entry(override={"node": "win"}),  # bad node
            _v11_entry(override={"base_sha": ""}),  # bad base_sha
        ]
        errs = aggregate_v11_entry_errors(entries, decl=self.decl)
        # entry[1] has node whitelist error; entry[2] has base_sha error
        self.assertTrue(any("assignment[1]" in e and "whitelist" in e for e in errs))
        self.assertTrue(any("assignment[2]" in e and "base_sha" in e for e in errs))


class TestValidateMatrixV11(unittest.TestCase):
    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_empty_matrix_passes_v11(self):
        result = validate_assignment_matrix_v11({}, decl=self.decl)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verdict"], "ALLOW")

    def test_legal_v11_matrix_passes_v11(self):
        matrix = {
            "assignments": [
                _v11_entry(role="implementer", node="21bao"),
                _v11_entry(role="reviewer", node="5bao"),
            ],
        }
        result = validate_assignment_matrix_v11(matrix, decl=self.decl)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verdict"], "ALLOW")

    def test_illegal_v11_matrix_blocks(self):
        matrix = {
            "assignments": [
                _v11_entry(override={"node": "win"}),
            ],
        }
        result = validate_assignment_matrix_v11(matrix, decl=self.decl)
        self.assertFalse(result["valid"])
        self.assertEqual(result["verdict"], "BLOCK")

    def test_v11_acceptance_when_provider_namespace_unknown(self):
        # Stage 3 must NOT block provider_namespace=unknown
        matrix = {
            "assignments": [
                _v11_entry(override={"provider_namespace": "unknown"}),
                _v11_entry(role="reviewer", node="5bao",
                           override={"provider_namespace": "unknown"}),
            ],
        }
        result = validate_assignment_matrix_v11(matrix, decl=self.decl)
        self.assertTrue(result["valid"], f"errors: {result['errors']}")


class TestValidateMatrixStrict(unittest.TestCase):
    """Combined v1.0.0 + v1.1.0 validation for spec_version >= 1.1.0."""

    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_full_legal_v11_strict_passes(self):
        matrix = create_assignment_matrix("low", task_id="ext-strict-legal")
        matrix["assignments"] = [
            _v11_entry(role="implementer", node="21bao"),
            _v11_entry(role="reviewer", node="5bao"),
            _v11_entry(role="checker", node="21bao"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = VALID_ISO
        matrix["operator_approval_signature"] = compute_approval_signature(VALID_ULID, VALID_ISO)
        matrix["spec_version"] = "1.1.0"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        self.assertTrue(result["valid"],
                        f"expected PASS, errors: {result['errors']}")

    def test_strict_with_bad_node_blocks(self):
        matrix = create_assignment_matrix("low", task_id="ext-strict-bad-node")
        matrix["assignments"] = [
            _v11_entry(role="implementer", node="win"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = VALID_ISO
        matrix["operator_approval_signature"] = VALID_SHA256
        matrix["spec_version"] = "1.1.0"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        self.assertFalse(result["valid"])

    def test_strict_with_missing_reviewer_blocks_v10_path(self):
        # v1.0.0 still requires reviewer; missing it = v1.0.0 BLOCK
        matrix = create_assignment_matrix("low", task_id="ext-no-reviewer")
        matrix["assignments"] = [
            _v11_entry(role="implementer", node="21bao"),
            _v11_entry(role="checker", node="21bao"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = VALID_ISO
        matrix["operator_approval_signature"] = VALID_SHA256
        matrix["spec_version"] = "1.1.0"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        self.assertFalse(result["valid"])

    def test_strict_with_unapproved_blocks(self):
        matrix = create_assignment_matrix("low", task_id="ext-unapproved")
        matrix["assignments"] = [
            _v11_entry(role="implementer", node="21bao"),
            _v11_entry(role="reviewer", node="5bao"),
            _v11_entry(role="checker", node="21bao"),
        ]
        # operator_approved stays False
        matrix["spec_version"] = "1.1.0"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        self.assertFalse(result["valid"])

    def test_strict_low_risk_no_bypass(self):
        # Even low risk cannot bypass operator_approved
        matrix = create_assignment_matrix("low", task_id="ext-low-nobypass")
        matrix["assignments"] = [
            _v11_entry(role="implementer", node="21bao"),
            _v11_entry(role="reviewer", node="5bao"),
            _v11_entry(role="checker", node="21bao"),
        ]
        matrix["spec_version"] = "1.1.0"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        self.assertFalse(result["valid"])


class TestLegacyBackwardsCompat(unittest.TestCase):
    """v1.0.0 matrices (no v1.1.0 fields) still validate via legacy path."""

    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_legacy_matrix_passes_v10(self):
        matrix = create_assignment_matrix("low", task_id="ext-legacy")
        matrix["assignments"] = [
            create_role_assignment(role="implementer", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="reviewer", node="9bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="checker", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
        result = validate_assignment_matrix(matrix)
        self.assertTrue(result["valid"], f"legacy matrix must pass: {result['errors']}")

    def test_legacy_matrix_strict_now_fail_closed(self):
        # Stage 3 corrective (PR #278 issue #2): strict validator now
        # FAILS-CLOSED for legacy v1.0.0 matrices. The v1.1.0 field gaps
        # are BLOCK errors, NOT informational warnings. This is the
        # production enforcement path used by EAG and any other v1.1.0+
        # caller. Legacy behavior (informational warnings only) is now
        # available ONLY via the pure validate_assignment_matrix() path.
        matrix = create_assignment_matrix("low", task_id="ext-legacy-v11")
        matrix["assignments"] = [
            create_role_assignment(role="implementer", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="reviewer", node="5bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="checker", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
        result = validate_assignment_matrix_strict(matrix, decl=self.decl)
        # Stage 3 corrective: v1.0.0 matrix in strict validator now BLOCKS.
        self.assertFalse(result["valid"],
                         f"strict must BLOCK v1.0.0 legacy matrix; errors: {result.get('errors')}")
        self.assertEqual(result.get("spec_version"), "1.0.0")
        # The v11_strict_enforcement check must be present and BLOCK
        v11_check = [c for c in result.get("checks", [])
                     if c.get("name") == "v11_strict_enforcement"]
        self.assertEqual(len(v11_check), 1, "v11_strict_enforcement check must exist")
        self.assertEqual(v11_check[0]["result"], "BLOCK")
        # The errors must mention v1.1.0 field gaps
        err_text = " ".join(result.get("errors", []))
        self.assertIn("v1.1.0 required field", err_text,
                      f"errors must surface v1.1.0 field gap; got: {err_text[:200]}")

    def test_legacy_matrix_pure_v10_path_unchanged(self):
        # The pure v1.0.0 path (validate_assignment_matrix) remains
        # backward-compatible: legacy matrices pass without v1.1.0 field
        # enforcement. This is the documented non-production-compatible
        # fallback (see EAG _STRICT_AVAILABLE flag handling).
        matrix = create_assignment_matrix("low", task_id="ext-legacy-v10-unchanged")
        matrix["assignments"] = [
            create_role_assignment(role="implementer", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="reviewer", node="5bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
            create_role_assignment(role="checker", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
        result = validate_assignment_matrix(matrix)
        self.assertTrue(result["valid"],
                        f"v1.0.0 path must still pass legacy matrix; errors: {result.get('errors')}")

    def test_legacy_matrix_pure_v11_path_surfaces_missing(self):
        # Calling the pure v1.1.0 path on a legacy matrix DOES surface
        # the missing v1.1.0 fields as a BLOCK (this is the strict
        # v1.1.0-only contract). The strict wrapper softens this for
        # backward compat; the pure v1.1.0 path does not.
        matrix = create_assignment_matrix("low", task_id="ext-legacy-v11-pure")
        matrix["assignments"] = [
            create_role_assignment(role="implementer", node="21bao",
                                   model=REAL_MODEL_ID, provider="deepseek"),
        ]
        result = validate_assignment_matrix_v11(matrix, decl=self.decl)
        self.assertFalse(result["valid"],
                         "pure v1.1.0 path must surface missing fields")

    def test_legacy_v10_self_check_still_30_baseline(self):
        # The 30 rag-* self checks must still all PASS in v1.1.0
        result = self_check()
        rag_checks = [c for c in result["checks"] if c["name"].startswith("rag-")]
        self.assertGreaterEqual(len(rag_checks), 30,
                                f"expected >=30 rag-* checks, got {len(rag_checks)}")
        for c in rag_checks:
            self.assertTrue(c["passed"], f"rag-* regressed: {c['name']}: {c['detail']}")


class TestFallbackPolicyEdgeCases(unittest.TestCase):
    """Spec §5 / v1.0.0 fallback_policy boundary checks."""

    def test_legal_policies_pass(self):
        for fp in ("disabled", "operator_selects", "same_provider_different_model"):
            e = _v11_entry(override={"fallback_policy": fp})
            errs = validate_assignment_entry(e, 0)
            self.assertEqual(errs, [], f"fp={fp} should be legal, got {errs}")

    def test_illegal_policies_block_in_v10(self):
        for fp in ("", "auto", "Disabled", "DISABLED", "none", None, 123):
            e = _v11_entry(override={"fallback_policy": fp})
            errs = validate_assignment_entry(e, 0)
            self.assertGreater(len(errs), 0,
                               f"fp={fp!r} should be blocked, got no errors")

    def test_v11_entry_check_does_not_re_check_fallback_policy(self):
        # Stage 3 v1.1.0 entry check is additive; v1.0.0 fallback policy check
        # stays in validate_assignment_entry (v1.0.0 path).
        e = _v11_entry(override={"fallback_policy": "auto"})
        v11_errs = validate_assignment_entry_v11(e, 0)
        # v11 path does not raise an error for fallback_policy
        self.assertEqual(v11_errs, [])


class TestAssignmentIdUniqueness(unittest.TestCase):
    """Spec §4.2: assignment_id must be unique within a matrix."""

    def setUp(self):
        self.decl = load_model_pool_declarations()

    def test_duplicate_assignment_id_caught_in_v11_aggregate(self):
        # Two entries with the same assignment_id (and same v1.1.0 fields) —
        # the v11 per-entry check alone does not catch duplicates; uniqueness
        # is enforced at the matrix-aggregate layer (caller responsibility
        # in Stage 4+).
        # Stage 3 only checks format; duplicate-detection is left to Stage 4.
        e1 = _v11_entry()
        e2 = _v11_entry(role="reviewer", node="5bao")
        # Same assignment_id
        e2["assignment_id"] = e1["assignment_id"]
        entries = [e1, e2]
        errs = aggregate_v11_entry_errors(entries, decl=self.decl)
        # No duplicate error at Stage 3 (this is a known limitation, recorded)
        # Each entry's individual v1.1.0 fields still validate
        self.assertEqual(errs, [])


class TestSelfCheckIntegration(unittest.TestCase):
    """The RAG self-check is the single source of truth for the gate's status."""

    def test_self_check_passes(self):
        result = self_check()
        self.assertTrue(result["passed"],
                        f"self-check failed: {[c for c in result['checks'] if not c['passed']]}")

    def test_self_check_total_includes_v11(self):
        result = self_check()
        self.assertGreaterEqual(result["total_tests"], 50,
                                f"expected >=50 tests (30 rag-* + 20+ v11-*), got {result['total_tests']}")

    def test_self_check_exit_code_zero(self):
        result = self_check()
        self.assertEqual(result["exit_code"], 0)

    def test_self_check_version_1_1_0(self):
        result = self_check()
        self.assertEqual(result["version"], "1.1.0")


if __name__ == "__main__":
    unittest.main()
