"""Tests for backend/app/services/batch_persister_core.py (B0.persist.core)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.batch_evaluator import (
    RankedBatch,
    ScoringResult,
)
from app.services.batch_persister_core import (
    DEFAULT_STATUS,
    build_application_row,
    build_application_rows,
    make_dedup_key,
)


# ── helpers ──────────────────────────────────────────────────────────


def _result(
    *,
    canonical_url="https://boards.greenhouse.io/acme/jobs/123",
    fit_score=4.2,
    error=None,
    title="Senior Engineer",
    company="Acme",
) -> ScoringResult:
    return ScoringResult(
        canonical_url=canonical_url,
        fit_score=fit_score,
        error=error,
        title=title,
        company=company,
    )


_FIXED_NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
_USER = "user-abc"
_BATCH = "batch-001"


# ── make_dedup_key ───────────────────────────────────────────────────


class TestMakeDedupKey:
    def test_deterministic(self) -> None:
        a = make_dedup_key(user_id=_USER, canonical_url="https://x/y")
        b = make_dedup_key(user_id=_USER, canonical_url="https://x/y")
        assert a == b

    def test_different_users_collide_zero(self) -> None:
        a = make_dedup_key(user_id="u1", canonical_url="https://x/y")
        b = make_dedup_key(user_id="u2", canonical_url="https://x/y")
        assert a != b

    def test_different_urls_collide_zero(self) -> None:
        a = make_dedup_key(user_id=_USER, canonical_url="https://x/y")
        b = make_dedup_key(user_id=_USER, canonical_url="https://x/z")
        assert a != b

    def test_length_32(self) -> None:
        k = make_dedup_key(user_id=_USER, canonical_url="https://x/y")
        assert len(k) == 32
        # Hex-only.
        int(k, 16)

    def test_unit_separator_prevents_concat_collision(self) -> None:
        # If we naively concatenated, ("ab", "cd") and ("a", "bcd")
        # would collide.  The \x1f separator prevents that.
        a = make_dedup_key(user_id="ab", canonical_url="cd")
        b = make_dedup_key(user_id="a", canonical_url="bcd")
        assert a != b


# ── build_application_row ────────────────────────────────────────────


class TestBuildApplicationRow:
    def test_minimal_required_fields(self) -> None:
        row = build_application_row(
            result=_result(),
            user_id=_USER,
            batch_id=_BATCH,
            now=_FIXED_NOW,
        )
        assert row["user_id"] == _USER
        assert row["status"] == DEFAULT_STATUS == "draft"
        assert row["title"] == "Senior Engineer"

    def test_confirmed_facts_shape(self) -> None:
        row = build_application_row(
            result=_result(),
            user_id=_USER,
            batch_id=_BATCH,
            now=_FIXED_NOW,
        )
        cf = row["confirmed_facts"]
        assert cf["source"] == "batch"
        assert cf["batch_id"] == _BATCH
        assert cf["canonical_url"] == "https://boards.greenhouse.io/acme/jobs/123"
        assert cf["dedup_key"] == make_dedup_key(
            user_id=_USER,
            canonical_url="https://boards.greenhouse.io/acme/jobs/123",
        )
        assert cf["company"] == "Acme"
        assert cf["title"] == "Senior Engineer"
        assert cf["imported_at"] == _FIXED_NOW.isoformat()

    def test_scores_shape(self) -> None:
        row = build_application_row(
            result=_result(fit_score=3.7),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        s = row["scores"]
        assert s["fit"] == 3.7
        assert s["source"] == "batch_scorer"
        assert s["scored_at"] == _FIXED_NOW.isoformat()
        assert "error" not in s

    def test_scores_includes_error_when_present(self) -> None:
        # Defensive path — caller shouldn't pass these but we don't
        # crash on it; row is tagged so a bug shows up in DB.
        row = build_application_row(
            result=_result(error="ai_error:Boom", fit_score=None),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["scores"]["error"] == "ai_error:Boom"
        assert row["scores"]["fit"] is None

    def test_default_now_is_used_when_omitted(self) -> None:
        before = datetime.now(timezone.utc)
        row = build_application_row(
            result=_result(), user_id=_USER, batch_id=_BATCH,
        )
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(row["confirmed_facts"]["imported_at"])
        assert before <= ts <= after

    def test_title_falls_back_to_company_when_title_blank(self) -> None:
        row = build_application_row(
            result=_result(title="", company="Acme Corp"),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["title"] == "Acme Corp"

    def test_title_falls_back_to_company_when_title_whitespace(self) -> None:
        row = build_application_row(
            result=_result(title="   ", company="Beta"),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["title"] == "Beta"

    def test_title_falls_back_to_url_hint_when_both_missing(self) -> None:
        row = build_application_row(
            result=_result(
                title=None, company=None,
                canonical_url="https://boards.greenhouse.io/acme/jobs/12345",
            ),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["title"] == "Untitled — 12345"

    def test_title_url_hint_uses_host_when_no_path(self) -> None:
        row = build_application_row(
            result=_result(title=None, company=None,
                           canonical_url="https://example.com/"),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["title"] == "Untitled — example.com"

    def test_title_url_hint_truncates_very_long_segment(self) -> None:
        long_seg = "x" * 200
        row = build_application_row(
            result=_result(title=None, company=None,
                           canonical_url=f"https://x/{long_seg}"),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        # Truncated to 48 + ellipsis.
        assert row["title"].startswith("Untitled — ")
        assert row["title"].endswith("…")
        assert len(row["title"]) < 80

    def test_company_blank_becomes_none_in_facts(self) -> None:
        row = build_application_row(
            result=_result(company="   "),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert row["confirmed_facts"]["company"] is None

    def test_idempotent_same_input_same_output(self) -> None:
        a = build_application_row(
            result=_result(), user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        b = build_application_row(
            result=_result(), user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert a == b

    def test_no_modules_or_org_id_keys_emitted(self) -> None:
        # Keep the row minimal so the table's DEFAULT for `modules`
        # and `org_id` (added in 20260321 migration) takes over.
        row = build_application_row(
            result=_result(), user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert "modules" not in row
        assert "org_id" not in row
        assert "id" not in row  # let DB generate it


# ── build_application_rows (batch) ───────────────────────────────────


class TestBuildApplicationRows:
    def _ranked(self, *results: ScoringResult) -> RankedBatch:
        return RankedBatch(
            ranked=tuple(results),
            below_threshold=tuple(),
            failed=tuple(),
        )

    def test_empty_returns_empty_tuple(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(), user_id=_USER, batch_id=_BATCH,
            now=_FIXED_NOW,
        )
        assert out == tuple()

    def test_one_row_per_ranked_entry(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b"),
                _result(canonical_url="https://x/c"),
            ),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert len(out) == 3
        urls = [r["confirmed_facts"]["canonical_url"] for r in out]
        assert urls == ["https://x/a", "https://x/b", "https://x/c"]

    def test_returns_tuple_not_list(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(_result()),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert isinstance(out, tuple)

    def test_excludes_below_threshold_and_failed(self) -> None:
        # Even if we shove entries into below_threshold/failed, the
        # builder must only emit rows for `ranked`.
        ranked = RankedBatch(
            ranked=(_result(canonical_url="https://x/r"),),
            below_threshold=(_result(canonical_url="https://x/b"),),
            failed=(_result(canonical_url="https://x/f", error="ai_error"),),
        )
        out = build_application_rows(
            ranked=ranked, user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        urls = [r["confirmed_facts"]["canonical_url"] for r in out]
        assert urls == ["https://x/r"]

    def test_all_rows_share_batch_id(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b"),
            ),
            user_id=_USER, batch_id="grp-42", now=_FIXED_NOW,
        )
        assert all(r["confirmed_facts"]["batch_id"] == "grp-42" for r in out)

    def test_all_rows_share_imported_at(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b"),
            ),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        ts = {r["confirmed_facts"]["imported_at"] for r in out}
        assert ts == {_FIXED_NOW.isoformat()}

    def test_all_rows_share_user_id(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b"),
            ),
            user_id="u-special", batch_id=_BATCH, now=_FIXED_NOW,
        )
        assert all(r["user_id"] == "u-special" for r in out)

    def test_dedup_keys_distinct_per_url(self) -> None:
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b"),
            ),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        keys = [r["confirmed_facts"]["dedup_key"] for r in out]
        assert len(set(keys)) == 2

    def test_jsonable(self) -> None:
        import json
        out = build_application_rows(
            ranked=self._ranked(
                _result(canonical_url="https://x/a"),
                _result(canonical_url="https://x/b", fit_score=None,
                        error="parse_error"),
            ),
            user_id=_USER, batch_id=_BATCH, now=_FIXED_NOW,
        )
        # Whole batch must round-trip through json.dumps.
        json.dumps(out)
