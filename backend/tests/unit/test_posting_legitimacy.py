"""Tests for backend/app/services/posting_legitimacy.py."""

from __future__ import annotations

import pytest

from app.services.liveness_classifier import MIN_CONTENT_CHARS
from app.services.posting_legitimacy import (
    LegitimacyTier,
    PostingLegitimacy,
    evaluate_posting_legitimacy,
)

LONG_BODY = "x" * (MIN_CONTENT_CHARS + 100)
GREENHOUSE_URL = "https://boards.greenhouse.io/acme/jobs/1234567"
LEVER_URL = "https://jobs.lever.co/acme/abc-123-def"
ASHBY_URL = "https://jobs.ashbyhq.com/acme/role-slug"
SELF_HOSTED_URL = "https://acme.com/careers/senior-engineer"


class TestGhostTier:
    def test_404_is_ghost(self) -> None:
        result = evaluate_posting_legitimacy(url=GREENHOUSE_URL, status=404)
        assert result.tier is LegitimacyTier.GHOST
        assert result.ats_provider == "greenhouse"
        assert any("removal" in r.lower() for r in result.reasoning)

    def test_410_is_ghost(self) -> None:
        result = evaluate_posting_legitimacy(url=GREENHOUSE_URL, status=410)
        assert result.tier is LegitimacyTier.GHOST

    def test_expired_phrase_is_ghost(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text="This job has expired. " + LONG_BODY,
        )
        assert result.tier is LegitimacyTier.GHOST

    def test_ghost_confidence_carries_through(self) -> None:
        result = evaluate_posting_legitimacy(url=GREENHOUSE_URL, status=404)
        assert result.confidence == 1.0


class TestLegitimateTier:
    def test_live_on_greenhouse_is_legitimate(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply for this job"],
        )
        assert result.tier is LegitimacyTier.LEGITIMATE
        assert result.ats_provider == "greenhouse"
        assert result.ats_company == "acme"
        assert result.confidence > 0.9  # bumped from 0.9

    @pytest.mark.parametrize("url", [GREENHOUSE_URL, LEVER_URL, ASHBY_URL])
    def test_live_on_known_ats_is_legitimate(self, url: str) -> None:
        result = evaluate_posting_legitimacy(
            url=url,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply"],
        )
        assert result.tier is LegitimacyTier.LEGITIMATE


class TestCautionTier:
    def test_live_self_hosted_is_caution(self) -> None:
        result = evaluate_posting_legitimacy(
            url=SELF_HOSTED_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply Now"],
        )
        assert result.tier is LegitimacyTier.CAUTION
        assert result.ats_provider is None
        assert any("recognized ATS" in r for r in result.reasoning)

    def test_high_repost_downgrades_legitimate_to_caution(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply"],
            repost_count=5,
        )
        assert result.tier is LegitimacyTier.CAUTION
        assert any("Downgraded LEGITIMATE" in r for r in result.reasoning)
        assert any(s.startswith("repost_count:") for s in result.signals)

    def test_old_posting_downgrades_legitimate_to_caution(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply"],
            age_days=120,
        )
        assert result.tier is LegitimacyTier.CAUTION
        assert any("age_days:120" in s for s in result.signals)

    def test_repost_under_threshold_no_downgrade(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply"],
            repost_count=2,
        )
        assert result.tier is LegitimacyTier.LEGITIMATE


class TestUnknownTier:
    def test_thin_content_is_unknown(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text="loading...",
        )
        assert result.tier is LegitimacyTier.UNKNOWN

    def test_unknown_with_known_ats_mentions_provenance(self) -> None:
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text="loading...",
        )
        assert any("greenhouse" in r.lower() for r in result.reasoning)

    def test_unknown_self_hosted(self) -> None:
        result = evaluate_posting_legitimacy(
            url=SELF_HOSTED_URL,
            status=200,
            body_text="loading...",
        )
        assert result.tier is LegitimacyTier.UNKNOWN
        assert result.ats_provider is None


class TestEthicalFraming:
    """HARD-RULE #3: never accuse a recruiter of dishonesty."""

    def test_no_accusatory_words_in_reasoning(self) -> None:
        import re

        forbidden = ["fraud", "scam", "fake", "lying", "dishonest", "deceptive"]
        scenarios = [
            evaluate_posting_legitimacy(url=GREENHOUSE_URL, status=404),
            evaluate_posting_legitimacy(
                url=GREENHOUSE_URL, status=200, body_text=LONG_BODY,
                apply_controls=["Apply"], repost_count=10,
            ),
            evaluate_posting_legitimacy(
                url=SELF_HOSTED_URL, status=200, body_text=LONG_BODY,
                apply_controls=["Apply"],
            ),
        ]
        for r in scenarios:
            joined = " ".join(r.reasoning).lower()
            for word in forbidden:
                pattern = re.compile(rf"\b{re.escape(word)}\b")
                assert not pattern.search(joined), (
                    f"Accusatory word {word!r} in: {joined!r}"
                )


class TestSerialization:
    def test_to_dict_round_trips_json(self) -> None:
        import json

        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL,
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply"],
        )
        d = result.to_dict()
        json.dumps(d)
        # Spot-check shape:
        assert d["tier"] == "legitimate"
        assert d["liveness"]["liveness"] == "live"
        assert isinstance(d["signals"], list)
        assert isinstance(d["reasoning"], list)
        assert d["evaluated_at"].endswith("Z")

    def test_evaluated_at_is_iso_utc(self) -> None:
        result = evaluate_posting_legitimacy(url=GREENHOUSE_URL, status=404)
        assert "T" in result.evaluated_at
        assert result.evaluated_at.endswith("Z")


class TestNoExceptions:
    def test_empty_url(self) -> None:
        result = evaluate_posting_legitimacy(url="")
        assert isinstance(result, PostingLegitimacy)
        assert result.url_canonical == ""
        assert result.ats_provider is None

    def test_pathological_age(self) -> None:
        # Negative age should not crash.
        result = evaluate_posting_legitimacy(
            url=GREENHOUSE_URL, status=200, body_text=LONG_BODY,
            apply_controls=["Apply"], age_days=-5,
        )
        assert isinstance(result, PostingLegitimacy)
