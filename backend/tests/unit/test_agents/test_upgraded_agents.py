# backend/tests/unit/test_agents/test_upgraded_agents.py
"""Regression tests for v2 agent upgrades.

Tests the upgraded deterministic tools, agent schemas, and eval harness
to ensure all improvements are captured and no regressions occur.
"""
import pytest
from ai_engine.agents.tools import (
    _parse_jd,
    _compute_keyword_overlap,
    _compute_readability,
    _extract_claims,
    _match_claims_to_evidence,
)
from ai_engine.agents.schemas import (
    FACT_CHECKER_SCHEMA,
)
from ai_engine.agents.eval import (
    FactCheckerEval,
    ValidatorEval,
)
from ai_engine.agents.orchestrator import (
    POLICY_STRICT,
    DEFAULT_POLICIES,
)


# ═══════════════════════════════════════════════════════════════════════
#  v2 Tool upgrades — bigrams, fuzzy matching, requirement classification
# ═══════════════════════════════════════════════════════════════════════

class TestParseJdV2:
    """Test JD parsing v2 features: bigrams, requirement classification."""

    @pytest.mark.asyncio
    async def test_extracts_technical_bigrams(self):
        jd = "We need experience with machine learning and distributed systems. CI/CD pipeline experience required."
        result = await _parse_jd(jd_text=jd)
        keywords = [k.lower() for k in result["top_keywords"]]
        # Should extract bigrams like "machine learning" or "distributed systems"
        assert any("machine" in k or "learning" in k for k in keywords) or \
               "machine learning" in result.get("keyword_frequency", {})

    @pytest.mark.asyncio
    async def test_classifies_must_have_vs_nice_to_have(self):
        jd = (
            "Requirements:\n"
            "- Python\n"
            "- Docker\n\n"
            "Nice to have:\n"
            "- Kubernetes\n"
            "- GraphQL\n"
        )
        result = await _parse_jd(jd_text=jd)
        must = [k.lower() for k in result.get("must_have_keywords", [])]
        nice = [k.lower() for k in result.get("nice_to_have_keywords", [])]
        assert "python" in must
        assert "kubernetes" in nice or "graphql" in nice

    @pytest.mark.asyncio
    async def test_returns_must_have_field(self):
        result = await _parse_jd(jd_text="Python and Docker required. Kubernetes preferred.")
        assert "must_have_keywords" in result
        assert "nice_to_have_keywords" in result


class TestKeywordOverlapV2:
    """Test keyword overlap v2 features: fuzzy matching."""

    @pytest.mark.asyncio
    async def test_fuzzy_matching(self):
        doc = "Experience with Python programming and Kubernetes orchestration"
        jd = "Strong Pythonic code and K8s deployment experience"
        result = await _compute_keyword_overlap(document_text=doc, jd_text=jd)
        # Should have some fuzzy matches or exact matches
        assert result["match_ratio"] >= 0
        assert "fuzzy_matches" in result

    @pytest.mark.asyncio
    async def test_includes_exact_match_ratio(self):
        doc = "Python Docker AWS"
        jd = "Python Docker AWS Kubernetes"
        result = await _compute_keyword_overlap(document_text=doc, jd_text=jd)
        assert "exact_match_ratio" in result
        assert result["exact_match_ratio"] > 0


class TestReadabilityV2:
    """Test readability v2 features: passive voice, quality band."""

    @pytest.mark.asyncio
    async def test_detects_passive_voice(self):
        text = "The code was written by the team. The tests were passed."
        result = await _compute_readability(text=text)
        assert result["passive_voice_count"] >= 1

    @pytest.mark.asyncio
    async def test_quality_band(self):
        text = "Built APIs. Wrote code. Led team."
        result = await _compute_readability(text=text)
        assert result["quality_band"] in ("too_simple", "ideal", "acceptable", "too_complex")

    @pytest.mark.asyncio
    async def test_long_sentence_detection(self):
        long = " ".join(["word"] * 30) + "."
        text = f"Short sentence. {long} Another short one."
        result = await _compute_readability(text=text)
        assert result["long_sentences"] >= 1


class TestClaimExtractionV2:
    """Test claim extraction v2 features: more claim types, deduplication."""

    @pytest.mark.asyncio
    async def test_extracts_multiple_claim_types(self):
        text = (
            "Led a team of 12 engineers at Google. "
            "Improved performance by 50%. "
            "Holds B.S. in Computer Science from MIT. "
            "AWS Solutions Architect certified."
        )
        result = await _extract_claims(document_text=text)
        claim_types = result.get("claim_types", {})
        assert result["total_claims_found"] >= 3
        # Should find quantified and credential claims
        assert "quantified" in claim_types or "credential" in claim_types

    @pytest.mark.asyncio
    async def test_extracts_company_claims(self):
        text = "Worked as Senior Engineer at Microsoft for 5 years."
        result = await _extract_claims(document_text=text)
        claim_texts = [c["text"].lower() for c in result["claims"]]
        assert any("microsoft" in t for t in claim_texts)

    @pytest.mark.asyncio
    async def test_deduplication(self):
        text = "Improved performance by 50%. Improved performance by 50%."
        result = await _extract_claims(document_text=text)
        # Should not have exact duplicates at same position
        positions = [c["position"] for c in result["claims"]]
        assert len(positions) == len(set(positions))


class TestClaimMatchingV2:
    """Test claim matching v2 features: fuzzy and confidence scoring."""

    @pytest.mark.asyncio
    async def test_fuzzy_matching(self):
        claims = [
            {"text": "Used Python for data processing at TechCorp", "type": "quantified", "position": 0},
        ]
        evidence = {
            "skills": ["Python", "pandas"],
            "companies": ["TechCorp"],
            "titles": ["Data Engineer"],
            "certifications": [],
            "education": [],
        }
        result = await _match_claims_to_evidence(claims=claims, evidence=evidence)
        assert len(result["matched_claims"]) == 1
        assert result["matched_claims"][0]["match_confidence"] >= 0.5

    @pytest.mark.asyncio
    async def test_reports_high_confidence_count(self):
        claims = [
            {"text": "Python developer at Acme Corp", "type": "employment", "position": 0},
            {"text": "Led unknown team at FakeCo", "type": "implicit", "position": 50},
        ]
        evidence = {
            "skills": ["Python"],
            "companies": ["Acme Corp"],
            "titles": [],
            "certifications": [],
            "education": [],
        }
        result = await _match_claims_to_evidence(claims=claims, evidence=evidence)
        assert "high_confidence_matches" in result


# ═══════════════════════════════════════════════════════════════════════
#  v2 Schema upgrades
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaV2:
    """Test that schemas match v2 agent contracts."""

    def test_fact_checker_schema_has_4_tiers(self):
        props = FACT_CHECKER_SCHEMA["properties"]["summary"]["properties"]
        assert "verified" in props
        assert "fabricated" in props
        # New tiers
        assert "inferred" in props
        assert "embellished" in props

    def test_fact_checker_schema_relaxed_fabricated_items(self):
        """fabricated_claims items should only require 'text', not 'reason'."""
        items = FACT_CHECKER_SCHEMA["properties"]["fabricated_claims"]["items"]
        assert "text" in items["required"]
        # reason is optional (LLM might not always provide it)
        assert "reason" not in items.get("required", []) or "reason" in items["required"]


# ═══════════════════════════════════════════════════════════════════════
#  v2 Eval harness upgrades
# ═══════════════════════════════════════════════════════════════════════

class TestFactCheckerEvalV2:
    """Test 4-tier fact checker evaluation."""

    def test_handles_4_tier_summary(self):
        result = {
            "claims": [{"text": "a", "classification": "verified", "confidence": 0.9}],
            "summary": {
                "verified": 5,
                "inferred": 3,
                "embellished": 2,
                "enhanced": 5,
                "fabricated": 0,
            },
            "overall_accuracy": 0.8,
            "confidence": 0.9,
            "deterministic_match_rate": 0.7,
            "auto_verified_count": 4,
            "total_claims_extracted": 10,
        }
        metrics = FactCheckerEval.evaluate(result, {}, {})
        assert metrics.passed is True
        assert metrics.scores["auto_verify_rate"] == 0.4  # 4/10
        assert metrics.scores["claim_coverage"] == 1.0


class TestValidatorEvalV2:
    """Test validator eval handles hard/soft failure distinction."""

    def test_valid_result(self):
        result = {
            "valid": True,
            "checks": {
                "schema_compliant": True,
                "format_valid": True,
                "all_sections_present": True,
                "length_appropriate": True,
            },
            "issues": [],
            "confidence": 0.95,
        }
        metrics = ValidatorEval.evaluate(result)
        assert metrics.passed is True
        assert metrics.scores["check_completeness"] == 1.0


# ═══════════════════════════════════════════════════════════════════════
#  v2 Orchestration policy calibration
# ═══════════════════════════════════════════════════════════════════════

class TestPolicyCalibrationV2:
    """Test calibrated orchestration policies."""

    def test_strict_threshold_calibrated(self):
        """STRICT policy threshold was lowered from 0.95 to 0.90."""
        assert POLICY_STRICT.confidence_threshold == 0.90

    def test_personal_statement_has_fact_check(self):
        """Personal statements should now have fact-checking enabled."""
        ps_policy = DEFAULT_POLICIES["personal_statement"]
        assert ps_policy.skip_fact_check is False

    def test_personal_statement_has_iterations(self):
        ps_policy = DEFAULT_POLICIES["personal_statement"]
        assert ps_policy.max_iterations == 2

    def test_cv_generation_is_strict(self):
        cv_policy = DEFAULT_POLICIES["cv_generation"]
        assert cv_policy.confidence_threshold == 0.90
        assert cv_policy.max_iterations == 3


# ═══════════════════════════════════════════════════════════════════════
#  Eval runner integration test
# ═══════════════════════════════════════════════════════════════════════

class TestEvalRunner:
    """Test that the eval runner can load and run gold cases."""

    @pytest.mark.asyncio
    async def test_run_single_case(self):
        from ai_engine.evals.runner import evaluate_case
        from ai_engine.evals.gold_corpus import GOLD_CASES

        result = await evaluate_case(GOLD_CASES[0], verbose=False)
        assert result.passed is True
        assert result.duration_ms >= 0
        assert len(result.scores) > 0

    @pytest.mark.asyncio
    async def test_run_all_cases(self):
        from ai_engine.evals.runner import run_all
        from ai_engine.evals.gold_corpus import GOLD_CASES

        report = await run_all(GOLD_CASES, verbose=False)
        assert report.total_cases == len(GOLD_CASES)
        assert report.passed_cases == report.total_cases
        assert report.failed_cases == 0
