"""AIM reviewer RAG wiring (PR m6-pr19b).

Verifies:
* Reviewer prompt gains the retrieved-sources Markdown block when the
  caller passes `retrieved_sources_markdown` in context, and the result
  metadata flips `rag_used=True`.
* Without the block, prompt is unchanged and `rag_used=False`.
* `generate_section` calls a supplied `source_retriever` exactly once
  per section (not per attempt) and threads the formatted block into
  every reviewer call.
"""
from __future__ import annotations

from typing import Any

import pytest

from ai_engine.agents.aim.reviewer import AIMReviewerAgent


# ── Fakes ────────────────────────────────────────────────────────────


class _FakeAIClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    async def complete_json(
        self, *, prompt: str, system: str, schema: dict, task_type: str,
        temperature: float,
    ) -> dict[str, Any]:
        self.last_prompt = prompt
        self.last_system = system
        return dict(self._response)


def _passing_reviewer_response() -> dict[str, Any]:
    sub = {
        "directive_alignment": 90,
        "analytical_depth": 90,
        "academic_tone": 90,
        "originality": 90,
        "structure": 90,
    }
    return {
        "sub_scores": sub,
        "ranked_issues": [],
        "summary": "ok",
        "confidence": 0.9,
    }


# ── Reviewer-level wiring ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reviewer_injects_retrieved_sources_markdown():
    fake = _FakeAIClient(_passing_reviewer_response())
    reviewer = AIMReviewerAgent(ai_client=fake)
    rag_md = "## Retrieved sources (RAG)\n\n- **Smith 2024** [peer_reviewed, relevance 0.91]\n  Summary line."

    result = await reviewer.run(
        {
            "section_content": "Some serious analytical body of text here.",
            "section_meta": {"title": "Discussion", "word_limit": 800},
            "parsed": {"directive": "analyse", "academic_level": "ug",
                       "rubric_breakdown": []},
            "recon": {"distinction_strategy": "argue from evidence"},
            "retrieved_sources_markdown": rag_md,
        }
    )

    assert "## Retrieved sources (RAG)" in (fake.last_prompt or "")
    assert "Smith 2024" in (fake.last_prompt or "")
    # Block sits before SECTION CONTENT so the model reads sources first.
    p = fake.last_prompt or ""
    assert p.index("Retrieved sources") < p.index("SECTION CONTENT")
    assert result.metadata["rag_used"] is True


@pytest.mark.asyncio
async def test_reviewer_omits_block_when_no_retrieved_sources():
    fake = _FakeAIClient(_passing_reviewer_response())
    reviewer = AIMReviewerAgent(ai_client=fake)

    result = await reviewer.run(
        {
            "section_content": "Some body text.",
            "section_meta": {"title": "Discussion", "word_limit": 800},
            "parsed": {"directive": "analyse"},
            "recon": {},
            # no retrieved_sources_markdown
        }
    )
    assert "Retrieved sources" not in (fake.last_prompt or "")
    assert result.metadata["rag_used"] is False


@pytest.mark.asyncio
async def test_reviewer_treats_blank_markdown_as_no_rag():
    fake = _FakeAIClient(_passing_reviewer_response())
    reviewer = AIMReviewerAgent(ai_client=fake)

    result = await reviewer.run(
        {
            "section_content": "Body",
            "section_meta": {"title": "X", "word_limit": 100},
            "parsed": {},
            "recon": {},
            "retrieved_sources_markdown": "   \n  ",
        }
    )
    assert "Retrieved sources" not in (fake.last_prompt or "")
    assert result.metadata["rag_used"] is False


# ── Pipeline-level wiring ────────────────────────────────────────────


class _FakeRetriever:
    def __init__(self, sources: list[Any] | None = None) -> None:
        self.sources = sources or []
        self.calls: list[dict[str, Any]] = []

    async def search(
        self, *, assignment_id: str, query: str, top_k: int = 5
    ) -> list[Any]:
        self.calls.append(
            {"assignment_id": assignment_id, "query": query, "top_k": top_k}
        )
        return list(self.sources)


@pytest.mark.asyncio
async def test_generate_section_threads_retriever_into_reviewer(monkeypatch):
    """generate_section calls retriever once and passes formatted MD."""
    from ai_engine.chains import aim_pipeline
    from ai_engine.rag import RetrievedSource

    captured_reviewer_ctxs: list[dict[str, Any]] = []
    captured_md = "## Retrieved sources (RAG)\n\n- **A** [peer_reviewed, relevance 0.80]\n  s"

    class _StubWriter:
        async def run(self, ctx):
            class R:
                content = {"content": "draft body", "blocks": [], "word_count": 2}
                latency_ms = 1
                flags: list[str] = []
            return R()

    class _StubReviewer:
        async def run(self, ctx):
            captured_reviewer_ctxs.append(ctx)

            class R:
                content = {"sub_scores": {}, "ranked_issues": [], "summary": ""}
                latency_ms = 1
                flags: list[str] = []
                quality_scores: dict[str, float] = {}
                metadata = {
                    "weighted_score": 95.0, "passed_gate": True,
                    "in_grey_zone": False, "rag_used": True,
                }
                feedback: dict[str, Any] = {}

            return R()

    monkeypatch.setattr(aim_pipeline, "AIMWriterAgent", lambda: _StubWriter())
    monkeypatch.setattr(aim_pipeline, "AIMReviewerAgent", lambda: _StubReviewer())

    src = RetrievedSource(
        id="11111111-1111-1111-1111-111111111111", title="A",
        summary="s", relevant_quotes=[], reliability_tier="peer_reviewed",
        score=0.8,
    )
    retriever = _FakeRetriever(sources=[src])

    result = await aim_pipeline.generate_section(
        section={"title": "Discussion", "word_limit": 800},
        parsed={"directive": "analyse"},
        recon={},
        max_attempts=1,
        source_retriever=retriever,
        assignment_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )

    # Retriever called exactly once for the section, regardless of attempts.
    assert len(retriever.calls) == 1
    call = retriever.calls[0]
    assert call["assignment_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert "analyse" in call["query"] and "Discussion" in call["query"]
    assert call["top_k"] == 5

    # Reviewer received a non-empty markdown block.
    assert captured_reviewer_ctxs, "reviewer was not invoked"
    md = captured_reviewer_ctxs[0]["retrieved_sources_markdown"]
    assert "## Retrieved sources (RAG)" in md
    assert result.final_attempt.passed_gate is True


@pytest.mark.asyncio
async def test_generate_section_skips_retriever_without_assignment(monkeypatch):
    """No assignment_id → retriever never called, reviewer ctx has empty MD."""
    from ai_engine.chains import aim_pipeline

    captured: list[dict[str, Any]] = []

    class _W:
        async def run(self, ctx):
            class R:
                content = {"content": "body", "blocks": [], "word_count": 1}
                latency_ms = 1
                flags: list[str] = []
            return R()

    class _Rv:
        async def run(self, ctx):
            captured.append(ctx)

            class R:
                content = {"sub_scores": {}, "ranked_issues": [], "summary": ""}
                latency_ms = 1
                flags: list[str] = []
                quality_scores: dict[str, float] = {}
                metadata = {"weighted_score": 95.0, "passed_gate": True,
                            "in_grey_zone": False, "rag_used": False}
                feedback: dict[str, Any] = {}
            return R()

    monkeypatch.setattr(aim_pipeline, "AIMWriterAgent", lambda: _W())
    monkeypatch.setattr(aim_pipeline, "AIMReviewerAgent", lambda: _Rv())

    retriever = _FakeRetriever()
    await aim_pipeline.generate_section(
        section={"title": "X", "word_limit": 100},
        parsed={"directive": "analyse"},
        recon={},
        max_attempts=1,
        source_retriever=retriever,
        # assignment_id omitted on purpose
    )
    assert retriever.calls == []
    assert captured[0]["retrieved_sources_markdown"] == ""
