"""S3-F3 — Behavioral tests for PipelineRuntime._build_evidence_summary.

The frontend evidence panel reads the structured summary returned by
this static helper. It must:
  * return None when there is nothing to summarize
  * count evidence items by tier from the ledger
  * count fabricated/unsupported citations
  * count unlinked citations (no evidence_ids)
  * stay defensive against malformed ledger / citation shapes
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.pipeline_runtime import PipelineRuntime


_summary = PipelineRuntime._build_evidence_summary  # type: ignore[attr-defined]


def _result(*, ledger=None, citations=None) -> SimpleNamespace:
    return SimpleNamespace(evidence_ledger=ledger, citations=citations)


def test_returns_none_when_pipeline_result_is_none() -> None:
    assert _summary(None) is None


def test_returns_none_when_neither_ledger_nor_citations() -> None:
    assert _summary(_result(ledger=None, citations=None)) is None
    assert _summary(_result(ledger={}, citations=[])) is None


def test_counts_tier_distribution_from_ledger_items() -> None:
    ledger = {
        "items": [
            {"tier": "primary"},
            {"tier": "primary"},
            {"tier": "secondary"},
            {"tier": "tertiary"},
        ]
    }
    out = _summary(_result(ledger=ledger, citations=[]))
    assert out is not None
    assert out["evidence_count"] == 4
    assert out["tier_distribution"] == {"primary": 2, "secondary": 1, "tertiary": 1}
    assert out["citation_count"] == 0


def test_unknown_tier_bucket_for_items_without_tier_key() -> None:
    ledger = {"items": [{"tier": "primary"}, {}, "not-a-dict"]}
    out = _summary(_result(ledger=ledger, citations=[]))
    assert out is not None
    assert out["tier_distribution"] == {"primary": 1, "unknown": 2}


def test_counts_fabricated_and_unsupported_citations() -> None:
    citations = [
        {"classification": "verified", "evidence_ids": ["e1"]},
        {"classification": "fabricated", "evidence_ids": ["e2"]},
        {"classification": "unsupported", "evidence_ids": ["e3"]},
        {"classification": "verified", "evidence_ids": ["e4"]},
    ]
    out = _summary(_result(ledger=None, citations=citations))
    assert out is not None
    assert out["citation_count"] == 4
    assert out["fabricated_count"] == 2  # fabricated + unsupported


def test_counts_unlinked_citations_missing_evidence_ids() -> None:
    citations = [
        {"classification": "verified", "evidence_ids": ["e1"]},
        {"classification": "verified", "evidence_ids": []},
        {"classification": "verified"},  # key missing entirely
    ]
    out = _summary(_result(ledger=None, citations=citations))
    assert out is not None
    assert out["unlinked_count"] == 2


def test_handles_non_list_items_using_count_field() -> None:
    """When ledger.items is present but not a list (degraded shape), the
    helper falls back to ledger.count for the total — without crashing."""
    out = _summary(_result(
        ledger={"items": "not-a-list", "count": 17},
        citations=[{"classification": "x"}],
    ))
    assert out is not None
    assert out["evidence_count"] == 17
    assert out["tier_distribution"] == {}


def test_combined_ledger_and_citations_full_envelope() -> None:
    out = _summary(_result(
        ledger={"items": [{"tier": "primary"}]},
        citations=[
            {"classification": "fabricated", "evidence_ids": ["e1"]},
            {"classification": "verified"},  # unlinked
        ],
    ))
    assert out == {
        "evidence_count": 1,
        "tier_distribution": {"primary": 1},
        "citation_count": 2,
        "fabricated_count": 1,
        "unlinked_count": 1,
    }
