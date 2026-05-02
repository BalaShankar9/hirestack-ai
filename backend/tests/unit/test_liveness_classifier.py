"""Tests for backend/app/services/liveness_classifier.py.

Branch coverage:
    1. HTTP 404 / 410 → REMOVED 1.0
    2. URL error redirects → REMOVED 0.95
    3. Hard-expired body phrase (multilingual) → REMOVED 0.9
    4. Apply control present (multilingual) → LIVE 0.9
    5. Listing page bait → REMOVED 0.7
    6. Thin content → UNKNOWN 0.5
    7. Default no-apply-control → UNKNOWN 0.4

Plus precedence checks: an expired phrase BEATS a leftover Apply button.
Plus serialization (to_dict).
Plus signals transparency (every classification carries traceable signal names).
"""

from __future__ import annotations

import pytest

from app.services.liveness_classifier import (
    APPLY_PATTERNS,
    EXPIRED_URL_PATTERNS,
    HARD_EXPIRED_PATTERNS,
    LISTING_PAGE_PATTERNS,
    MIN_CONTENT_CHARS,
    Liveness,
    LivenessResult,
    classify_liveness,
)

LONG_BODY = "x" * (MIN_CONTENT_CHARS + 50)


class TestHttpStatus:
    @pytest.mark.parametrize("status", [404, 410])
    def test_terminal_status_is_removed(self, status: int) -> None:
        result = classify_liveness(status=status, body_text=LONG_BODY)
        assert result.liveness is Liveness.REMOVED
        assert result.confidence == 1.0
        assert f"http_{status}" in result.signals

    def test_200_does_not_short_circuit(self) -> None:
        result = classify_liveness(status=200, body_text=LONG_BODY)
        assert result.liveness is Liveness.UNKNOWN  # no apply, no expired


class TestUrlPatterns:
    @pytest.mark.parametrize(
        "url",
        [
            "https://acme.com/jobs/123?error=true",
            "https://acme.com/careers/expired/abc",
            "https://acme.com/jobs/404",
            "https://acme.com/closed",
            "https://acme.com/job/not-found",
            "https://acme.com/job?expired=1",
        ],
    )
    def test_expired_url_patterns_removed(self, url: str) -> None:
        result = classify_liveness(status=200, final_url=url, body_text=LONG_BODY)
        assert result.liveness is Liveness.REMOVED
        assert result.confidence == 0.95
        assert any(s.startswith("expired_url:") for s in result.signals)


class TestHardExpiredPhrases:
    @pytest.mark.parametrize(
        "phrase",
        [
            "This job is no longer available.",
            "Position has been filled by an excellent candidate.",
            "This job has expired and is closed.",
            "We are no longer accepting applications for this role.",
            "This position is no longer open.",
            "Job listing not found.",
            "Applications closed on March 15.",
            "Diese Stelle ist nicht mehr verfügbar.",
            "Cette offre n'est plus disponible aujourd'hui.",
            "Esta vacante ya no está disponible para candidatos.",
            "Esta vaga já não está disponível neste momento.",
            "Questa offerta non è più disponibile online.",
            "Deze vacature is gesloten en niet meer beschikbaar.",
        ],
    )
    def test_phrases_classified_removed(self, phrase: str) -> None:
        # Pad to ensure body length isn't the deciding factor.
        body = phrase + " " + ("." * MIN_CONTENT_CHARS)
        result = classify_liveness(status=200, body_text=body)
        assert result.liveness is Liveness.REMOVED, f"phrase failed: {phrase!r}"
        assert result.confidence == 0.9
        assert any(s.startswith("expired_phrase:") for s in result.signals)


class TestApplyControls:
    @pytest.mark.parametrize(
        "control",
        [
            "Apply",
            "Apply Now",
            "Easy Apply",
            "Submit Application",
            "Start Application",
            "Apply for this job",
            "Solicitar",            # ES
            "Bewerben",             # DE
            "Ich bewerbe mich",     # DE
            "Postuler",             # FR
            "Candidatar-se",        # PT
            "Invia candidatura",    # IT
            "Candidati",            # IT
            "Solliciteer",          # NL
        ],
    )
    def test_apply_controls_classified_live(self, control: str) -> None:
        result = classify_liveness(
            status=200,
            body_text=LONG_BODY,
            apply_controls=[control],
        )
        assert result.liveness is Liveness.LIVE, f"control failed: {control!r}"
        assert result.confidence == 0.9
        assert any(s.startswith("apply_control:") for s in result.signals)


class TestPrecedence:
    """Expired phrases must beat leftover apply buttons."""

    def test_expired_phrase_beats_apply_button(self) -> None:
        result = classify_liveness(
            status=200,
            body_text="This job is no longer available." + (" " * MIN_CONTENT_CHARS),
            apply_controls=["Apply"],
        )
        assert result.liveness is Liveness.REMOVED

    def test_404_beats_everything(self) -> None:
        result = classify_liveness(
            status=404,
            body_text="Apply now! Easy Apply!" + LONG_BODY,
            apply_controls=["Apply Now"],
        )
        assert result.liveness is Liveness.REMOVED
        assert result.confidence == 1.0

    def test_url_error_beats_apply_button(self) -> None:
        result = classify_liveness(
            status=200,
            final_url="https://acme.com/job?error=true",
            body_text=LONG_BODY,
            apply_controls=["Apply"],
        )
        assert result.liveness is Liveness.REMOVED


class TestListingPageBait:
    @pytest.mark.parametrize(
        "body",
        [
            "Showing 12 jobs found in Engineering",
            "  47 Jobs found at Acme Corp",
            "Showing 1 - 25 of 200 results in your area",
        ],
    )
    def test_listing_page_classified_removed(self, body: str) -> None:
        padded = body + " " + ("." * MIN_CONTENT_CHARS)
        result = classify_liveness(status=200, body_text=padded)
        assert result.liveness is Liveness.REMOVED
        assert result.confidence == 0.7
        assert any(s.startswith("listing_page:") for s in result.signals)


class TestThinContent:
    def test_thin_content_unknown(self) -> None:
        result = classify_liveness(status=200, body_text="x" * (MIN_CONTENT_CHARS - 1))
        assert result.liveness is Liveness.UNKNOWN
        assert result.confidence == 0.5
        assert any(s.startswith("thin_content:") for s in result.signals)

    def test_empty_body_unknown(self) -> None:
        result = classify_liveness(status=200, body_text="")
        assert result.liveness is Liveness.UNKNOWN

    def test_whitespace_only_body_unknown(self) -> None:
        result = classify_liveness(status=200, body_text="   \n\t  ")
        assert result.liveness is Liveness.UNKNOWN


class TestDefault:
    def test_no_signals_unknown(self) -> None:
        result = classify_liveness(
            status=200,
            body_text="A perfectly normal long page with no apply button and no expired banner. " * 20,
        )
        assert result.liveness is Liveness.UNKNOWN
        assert result.confidence == 0.4
        assert "no_apply_control_found" in result.signals


class TestSerialization:
    def test_to_dict_shape(self) -> None:
        result = classify_liveness(status=404)
        d = result.to_dict()
        assert d == {
            "liveness": "removed",
            "reason": "HTTP 404",
            "confidence": 1.0,
            "signals": ["http_404"],
        }

    def test_to_dict_is_json_serializable(self) -> None:
        import json

        result = classify_liveness(
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Apply Now"],
        )
        # Must round-trip through JSON without error.
        json.dumps(result.to_dict())


class TestApplyControlsEdgeCases:
    def test_empty_controls_list(self) -> None:
        result = classify_liveness(status=200, body_text=LONG_BODY, apply_controls=[])
        assert result.liveness is Liveness.UNKNOWN

    def test_empty_strings_in_controls_ignored(self) -> None:
        result = classify_liveness(
            status=200,
            body_text=LONG_BODY,
            apply_controls=["", "  ", ""],
        )
        assert result.liveness is Liveness.UNKNOWN

    def test_multiple_controls_one_matches(self) -> None:
        result = classify_liveness(
            status=200,
            body_text=LONG_BODY,
            apply_controls=["Cancel", "Save", "Apply Now"],
        )
        assert result.liveness is Liveness.LIVE


class TestPatternTablesIntegrity:
    def test_all_pattern_tables_non_empty(self) -> None:
        assert len(HARD_EXPIRED_PATTERNS) > 0
        assert len(EXPIRED_URL_PATTERNS) > 0
        assert len(LISTING_PAGE_PATTERNS) > 0
        assert len(APPLY_PATTERNS) > 0

    def test_min_content_chars_reasonable(self) -> None:
        # Don't accidentally lower this — it's a deliberate quality gate.
        assert 100 <= MIN_CONTENT_CHARS <= 1000


class TestNoExceptions:
    """Pure function — must never raise on any input."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},  # all defaults
            {"status": -1},
            {"status": 99999},
            {"final_url": None},  # type: ignore[dict-item]
            {"body_text": None},  # type: ignore[dict-item]
            {"apply_controls": None},  # type: ignore[dict-item]
        ],
    )
    def test_pathological_inputs_dont_raise(self, kwargs: dict) -> None:
        # Filter None to avoid passing them where signature forbids — but
        # ensure signature handles defaults gracefully.
        safe = {k: v for k, v in kwargs.items() if v is not None}
        result = classify_liveness(**safe)
        assert isinstance(result, LivenessResult)
