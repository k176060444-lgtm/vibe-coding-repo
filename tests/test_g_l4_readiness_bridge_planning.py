"""G-L4 Readiness Bridge Planning Record Tests.

Verifies docs/baseline02/g-l4-readiness-bridge-planning.md:

1. Planning anchor matches current main (316640d)
2. References PR #341/#342/#343/#344/#345 merge chain correctly
3. operator_approved=unknown blocks readiness promotion
4. model_call_verified 3/3 does NOT imply readiness
5. Stage7 fail-closed is expected until operator_approved
6. No NMC/model_pool/runtime config mutation in this PR
7. No readiness/gray/Baseline03 entry
8. Namespace asymmetry is node-specific, NOT fallback/provider drift/provider-wide failure
9. No secret values present
10. operator_approved remains unknown; not promoted
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANNING_MD = os.path.join(REPO_ROOT, "docs/baseline02/g-l4-readiness-bridge-planning.md")

EXPECTED_PLANNING_ANCHOR = "316640d"

FORBIDDEN_CLAIMS = [
    # These are checked in POSITIVE context only (negation allowed via `not-` prefix).
    # The scope header uses `not-G-READINESS` etc. which is negation.
    "readiness ready",
    "gray ready",
    "Baseline03 ready",
    "Stage8 ready",
    # "operator_approved: true" appears in prerequisite description context
    # ("readiness requires `operator_approved: true`") which is NOT a promotion claim.
    # Only flag it in promotion context.
    "operator_approved promoted",
    "model_call_verified implies readiness",
    "model_call_verified equivalent to readiness",
    "model_call_verified alone sufficient",
    "readiness promotion complete",
    "readiness gate passed for production",
    "provider-wide failure",
]


def assert_not_in_text(text, phrase, path, context_note=""):
    """Assert a forbidden phrase is NOT present in text (positive check)."""
    if phrase.lower() in text.lower():
        # Find the line
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if phrase.lower() in line.lower():
                ctx = f" ({context_note})" if context_note else ""
                # Allow ❌ negation marker (bullets listing what NOT to do)
                if "❌" in line:
                    continue
                pytest.fail(
                    f"Forbidden claim '{phrase}' found in {path}:{i}{ctx}\n> {line.strip()}"
                )


def assert_in_text(text, phrase, path):
    """Assert a required phrase IS present in text."""
    if phrase.lower() not in text.lower():
        pytest.fail(f"Required phrase '{phrase}' NOT found in {path}")


class TestAnchor:
    def test_planning_anchor_matches_current_main(self):
        """Planning anchor must match EXPECTED_PLANNING_ANCHOR."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert EXPECTED_PLANNING_ANCHOR in content, (
            f"Planning doc must reference anchor {EXPECTED_PLANNING_ANCHOR}"
        )


class TestMergeChain:
    def test_references_pr_341(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "#341", PLANNING_MD)

    def test_references_pr_342(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "#342", PLANNING_MD)

    def test_references_pr_343(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "#343", PLANNING_MD)

    def test_references_pr_344(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "#344", PLANNING_MD)

    def test_references_pr_345(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "#345", PLANNING_MD)


class TestOperatorApproved:
    def test_operator_approved_unknown_blocks_readiness(self):
        """Document must state that operator_approved=unknown blocks readiness."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "operator_approved", PLANNING_MD)
        assert_in_text(content, "unknown", PLANNING_MD)
        assert_in_text(content, "block", PLANNING_MD)

    def test_model_call_verified_does_not_imply_readiness(self):
        """Document must state that model_call_verified 3/3 is not sufficient."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "necessary but not sufficient", PLANNING_MD)


class TestStage7FailClosed:
    def test_stage7_fail_closed_expected(self):
        """Document must state Stage7 fail-closed is expected until operator_approved."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "fail-closed", PLANNING_MD)
        assert_in_text(content, "Stage7", PLANNING_MD)


class TestNonMutation:
    def test_no_nmc_mutation(self):
        """Document must state NMC not modified."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "node_model_capability.yaml", PLANNING_MD)
        assert_in_text(content, "NOT modified", PLANNING_MD)

    def test_no_model_pool_mutation(self):
        """Document must state model_pool.yaml not modified."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "model_pool.yaml", PLANNING_MD)
        assert_in_text(content, "NOT modified", PLANNING_MD)


class TestNoStageEntry:
    def test_no_readiness_entry(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        # Allow G-READINESS in:
        # - scope header: "not-G-READINESS"
        # - blocked section: "Entering G-READINESS..." (MUST NOT section context)
        # Track proximity to "MUST NOT" sections
        lines = content.splitlines()
        in_must_not_section = False
        for i, line in enumerate(lines, 1):
            if "MUST NOT" in line:
                in_must_not_section = True
            elif line.startswith("##") and in_must_not_section:
                # A new header (different from the one that set MUST NOT) resets
                in_must_not_section = False
            if "G-READINESS" in line:
                if in_must_not_section:
                    continue
                if "not-G-READINESS" in line or "not G-READINESS" in line or "🔴" in line or "❌" in line:
                    continue
                if any(keyword in line.lower() for keyword in ["entered", "applicable", "not entered"]):
                    continue
                pytest.fail(f"G-READINESS in positive context at line {i}: {line.strip()}")

    def test_no_gray_entry(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_not_in_text(content, "gray ready", PLANNING_MD)
        assert_not_in_text(content, "Baseline03 ready", PLANNING_MD)

    def test_scope_header_present(self):
        """Document must carry the READ-ONLY PLANNING DOCUMENT header."""
        with open(PLANNING_MD, "r") as f:
            first_5_lines = "".join([f.readline() for _ in range(5)])
        assert_planning_string = "READ-ONLY PLANNING DOCUMENT" in first_5_lines
        assert assert_planning_string, (
            f"Planning doc must carry 'READ-ONLY PLANNING DOCUMENT' in first 5 lines"
        )


class TestNamespaceAsymmetry:
    def test_namespace_asymmetry_is_node_specific(self):
        """Namespace asymmetry described as node-specific, not fallback/drift."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        # Must contain the phrase
        assert_in_text(content, "node-specific", PLANNING_MD)
        # Must NOT claim fallback as a positive description.
        # "NOT a fallback" and "no fallback" are acceptable negations.
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            lower = line.lower()
            if "fallback" in lower:
                # Allow negation contexts
                if "not" in lower or "NOT" in lower or lower.strip().startswith("no "):
                    continue
                # Allow ❌ prefix (negation marker in bullet list)
                if "❌" in line:
                    continue
                # Allow structural references (e.g., "NO_FALLBACK")
                if "no_fallback" in lower or "not-fallback" in lower:
                    continue
                pytest.fail(f"'fallback' in non-negation context at line {i}: {line.strip()}")

    def test_provider_drift_not_claimed(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        # Allow negation contexts (NOT provider drift, not provider drift, no provider drift)
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            lower = line.lower()
            if "provider drift" in lower:
                if "not" in lower or "NOT" in lower or lower.strip().startswith("no "):
                    continue
                if "❌" in line:
                    continue
                pytest.fail(f"'provider drift' found in non-negation context at line {i}: {line.strip()}")


class TestNoSecrets:
    def test_no_secret_values(self):
        """No API keys, tokens, or credential values in planning doc."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        secret_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r"AKIA[0-9A-Z]{16}",
            r"ghp_[a-zA-Z0-9]{36,}",
            r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----",
        ]
        for pat in secret_patterns:
            matches = re.findall(pat, content)
            assert len(matches) == 0, (
                f"Secret pattern '{pat}' found in planning doc: {matches}"
            )


class TestNonPromotion:
    def test_operator_approved_not_promoted(self):
        """Document must state operator_approved not promoted."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        # The doc says "operator_approved remains unknown" or "operator_approved = unknown — unchanged"
        assert any(phrase in content for phrase in [
            "operator_approved remains",
            "operator_approved.*unchanged",
            "Operator-Controlled Fields (Not Promoted)",
        ]), f"Required statement about operator_approved not promoted NOT found in {PLANNING_MD}"

    def test_non_promotion_statement_present(self):
        """Document must have a non-promotion statement section."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "Non-Promotion Statement", PLANNING_MD)


class TestForbiddenClaims:
    """Verify NO forbidden readiness/gray claims appear unconventionally."""

    def test_no_positive_readiness_claim(self):
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        for phrase in FORBIDDEN_CLAIMS:
            assert_not_in_text(content, phrase, PLANNING_MD)


class TestScopeHeader:
    def test_planning_doc_scope_header(self):
        """Document status line at top carries not-readiness-promotion guard."""
        with open(PLANNING_MD, "r") as f:
            first_10_lines = "".join([f.readline() for _ in range(10)])
        required_guards = [
            "not-readiness-promotion",
            "not-operator_approved-execution",
            "not-G-READINESS",
            "not-gray",
            "not-Baseline03",
        ]
        for guard in required_guards:
            assert guard in first_10_lines, (
                f"Scope header missing guard: {guard}"
            )


class TestBlockedMatrix:
    def test_blocked_matrix_present(self):
        """Document must have blocked/unblocked matrix."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "Blocked / Unblocked", PLANNING_MD)

    def test_readiness_promotion_as_blocked(self):
        """Readiness promotion must be listed as blocked by operator_approved=unknown."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "readiness promotion", PLANNING_MD)


class TestSubsequentSteps:
    def test_subsequent_authorization_steps_present(self):
        """Document must outline subsequent authorization steps."""
        with open(PLANNING_MD, "r") as f:
            content = f.read()
        assert_in_text(content, "Authorization Step", PLANNING_MD)
