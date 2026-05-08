"""
AIM \u2014 Pipeline Orchestrator.

Two entry points consumed by the API layer:

    analyze_assignment(brief_text, rubric_text)
        \u2192 Parser  \u2192 Recon  \u2192 returns AnalysisResult
        Halts after Parser if confidence < 0.9.

    generate_section(section, parsed, recon, *, max_attempts=3, min_improvement=5)
        \u2192 Writer (\u2192 Reviewer)\u2715 loop with diminishing-returns stop, plus
        optional grey-zone Pro escalation on the 2nd reviewer pass.

    predict_grade(parsed, section_reviews) \u2192 GradePrediction
    fix_section(section, parsed, draft) \u2192 FixDiagnostic
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from ai_engine.agents.aim import (
    AIMFixAgent,
    AIMGradePredictorAgent,
    AIMParserAgent,
    AIMReconAgent,
    AIMReviewerAgent,
    AIMWriterAgent,
)
from ai_engine.agents.aim.reviewer import GREY_ZONE, PASS_THRESHOLD


# ── Streaming emitter ──────────────────────────────────────────────────
# Callable bridge so this module never imports the backend SSE sink.
# Signature: emit(event_type, *, agent="", status="", message="", progress=0, data=None)
AIMEmitter = Callable[..., Awaitable[None]]


async def _noop_emitter(*_a: Any, **_kw: Any) -> None:  # pragma: no cover - trivial
    return None


def _attempt_progress(attempt: int, max_attempts: int, *, phase: str) -> int:
    """Map (attempt, phase) onto a 0..100 progress slot for the live UI.

    Each attempt occupies an equal slice. Within an attempt: writer 0%-50%,
    reviewer 50%-100% of the slice. Final cap at 99 so 100 is reserved for
    the orchestrator-emitted ``complete`` event.
    """
    n = max(1, max_attempts)
    base = int((attempt - 1) * (100 / n))
    span = int(100 / n)
    offsets = {"writer": 0, "writer_done": int(span * 0.4),
               "reviewer": int(span * 0.5), "reviewer_done": int(span * 0.9)}
    return min(99, base + offsets.get(phase, 0))


# ── Public API ────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    parsed: dict[str, Any]
    recon: Optional[dict[str, Any]]
    needs_clarification: bool
    clarification_questions: list[dict[str, Any]] = field(default_factory=list)
    parser_confidence: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class SectionAttempt:
    version: int
    content: str
    blocks: list[dict[str, Any]]
    word_count: int
    reviewer: dict[str, Any]
    weighted_score: float
    passed_gate: bool
    model_used: str | None = None
    latency_ms: int = 0


@dataclass
class SectionGenerationResult:
    section_id: str | None
    final_attempt: SectionAttempt
    history: list[SectionAttempt]
    final_passed_gate: bool
    stop_reason: str          # "passed" | "max_attempts" | "diminishing_returns"


async def analyze_assignment(
    brief_text: str,
    rubric_text: str = "",
    *,
    emit: Optional[AIMEmitter] = None,
) -> AnalysisResult:
    e = emit or _noop_emitter
    parser = AIMParserAgent()
    await e("agent_status", agent="parser", status="running",
            message="Extracting assignment brief", progress=10)
    parsed_result = await parser.run({"brief_text": brief_text, "rubric_text": rubric_text})
    parsed = parsed_result.content
    needs_clar = "needs_clarification" in parsed_result.flags
    await e("agent_status", agent="parser", status="completed",
            message=("Directive detected: " + str(parsed.get("directive") or "?")),
            progress=30,
            data={"directive": parsed.get("directive"),
                  "confidence": parsed.get("confidence"),
                  "needs_clarification": needs_clar})
    if needs_clar:
        return AnalysisResult(
            parsed=parsed,
            recon=None,
            needs_clarification=True,
            clarification_questions=parsed.get("clarification_questions") or [],
            parser_confidence=float(parsed.get("confidence", 0.0)),
            flags=parsed_result.flags,
        )
    recon = AIMReconAgent()
    await e("agent_status", agent="recon", status="running",
            message="Analysing rubric and distinction strategy", progress=50)
    recon_result = await recon.run({"parsed": parsed, "brief_text": brief_text})
    await e("agent_status", agent="recon", status="completed",
            message="Rubric weights identified", progress=80,
            data={"sections": len((recon_result.content or {}).get("section_strategy") or [])})
    return AnalysisResult(
        parsed=parsed,
        recon=recon_result.content,
        needs_clarification=False,
        parser_confidence=float(parsed.get("confidence", 0.0)),
        flags=parsed_result.flags + recon_result.flags,
    )


async def generate_section(
    section: dict[str, Any],
    parsed: dict[str, Any],
    recon: dict[str, Any],
    *,
    section_id: str | None = None,
    max_attempts: int = 3,
    min_improvement: float = 5.0,
    emit: Optional[AIMEmitter] = None,
    # PR m6-pr19b: optional RAG context. When `source_retriever` and
    # `assignment_id` are both supplied (caller gates on ff_aim_rag),
    # the reviewer prompt gains a top-k retrieved sources block. Pure
    # additive — omit either to preserve previous behaviour.
    source_retriever: Any = None,
    assignment_id: str | None = None,
    rag_top_k: int = 5,
) -> SectionGenerationResult:
    if not section or not section.get("title") or not section.get("word_limit"):
        raise ValueError("generate_section: section must include title and word_limit")

    e = emit or _noop_emitter
    writer = AIMWriterAgent()
    reviewer = AIMReviewerAgent()
    history: list[SectionAttempt] = []
    previous_attempt_text: str | None = None
    previous_issues: list[dict] = []
    previous_score = 0.0

    # Pull section-specific scoring logic from recon.section_strategy if present
    scoring_logic = ""
    for s in (recon.get("section_strategy") or []):
        if s.get("section_title") == section.get("title"):
            scoring_logic = s.get("scoring_logic", "")
            break

    section_title = str(section.get("title") or "")

    # PR m6-pr19b: pre-compute the RAG block once per section. The query
    # is `directive + section title` — stable across writer attempts so
    # we only embed/RPC once. Failures here are non-fatal: emit a
    # warning event and the reviewer runs without retrieved sources.
    retrieved_md = ""
    if source_retriever is not None and assignment_id:
        try:
            from ai_engine.rag import format_sources_for_prompt

            rag_query = (
                f"{parsed.get('directive', '')} {section_title}".strip()
                or section_title
            )
            retrieved = await source_retriever.search(
                assignment_id=assignment_id,
                query=rag_query,
                top_k=rag_top_k,
            )
            retrieved_md = format_sources_for_prompt(retrieved)
        except Exception as exc:  # pragma: no cover - defensive
            await e(
                "agent_status",
                agent="reviewer",
                status="warning",
                message=f"RAG retrieval failed; continuing without sources ({exc!s})",
                data={"section_id": section_id},
            )
            retrieved_md = ""

    for attempt_num in range(1, max_attempts + 1):
        # 1) Writer
        write_ctx = {
            "section": section,
            "parsed": parsed,
            "recon": recon,
            "scoring_logic": scoring_logic,
        }
        if previous_attempt_text:
            write_ctx["previous_attempt"] = previous_attempt_text
            write_ctx["reviewer_issues"] = previous_issues

        await e("agent_status", agent="writer", status="running",
                message=f"Drafting {section_title} (attempt {attempt_num}/{max_attempts})",
                progress=_attempt_progress(attempt_num, max_attempts, phase="writer"),
                data={"section_id": section_id, "attempt": attempt_num})
        wresult = await writer.run(write_ctx)
        content_text = (wresult.content.get("content") or "").strip()
        blocks = wresult.content.get("blocks") or []
        word_count = int(wresult.content.get("word_count") or len(content_text.split()))
        await e("agent_status", agent="writer", status="completed",
                message=f"Draft ready ({word_count} words)",
                progress=_attempt_progress(attempt_num, max_attempts, phase="writer_done"),
                latency_ms=wresult.latency_ms,
                data={"section_id": section_id, "attempt": attempt_num,
                      "word_count": word_count})

        # 2) Reviewer (escalate to Pro on attempt 2 if previous score in grey zone)
        escalate = (
            attempt_num >= 2
            and GREY_ZONE[0] <= previous_score < GREY_ZONE[1]
        )
        await e("agent_status", agent="reviewer", status="running",
                message=("Evaluating quality (Pro escalation)" if escalate
                         else "Evaluating quality"),
                progress=_attempt_progress(attempt_num, max_attempts, phase="reviewer"),
                data={"section_id": section_id, "attempt": attempt_num,
                      "escalated": escalate})
        rresult = await reviewer.run({
            "section_content": content_text,
            "section_meta": section,
            "parsed": parsed,
            "recon": recon,
            "escalate_to_pro": escalate,
            "retrieved_sources_markdown": retrieved_md,
        })
        weighted = float(rresult.metadata.get("weighted_score", 0.0))
        passed = bool(rresult.metadata.get("passed_gate"))

        attempt = SectionAttempt(
            version=attempt_num,
            content=content_text,
            blocks=blocks,
            word_count=word_count,
            reviewer=rresult.content,
            weighted_score=weighted,
            passed_gate=passed,
            model_used=None,
            latency_ms=wresult.latency_ms + rresult.latency_ms,
        )
        history.append(attempt)

        await e("agent_status", agent="reviewer", status="completed",
                message=f"Quality score: {weighted:.1f}/100",
                progress=_attempt_progress(attempt_num, max_attempts, phase="reviewer_done"),
                latency_ms=rresult.latency_ms,
                data={"section_id": section_id, "attempt": attempt_num,
                      "weighted_score": weighted, "passed_gate": passed,
                      "verdict": (rresult.content or {}).get("verdict")})
        await e("attempt", agent="reviewer", status="completed",
                message=f"Attempt {attempt_num} complete",
                progress=_attempt_progress(attempt_num, max_attempts, phase="reviewer_done"),
                latency_ms=attempt.latency_ms,
                data={
                    "version": attempt.version,
                    "content": attempt.content,
                    "blocks": attempt.blocks,
                    "word_count": attempt.word_count,
                    "weighted_score": attempt.weighted_score,
                    "passed_gate": attempt.passed_gate,
                    "reviewer": attempt.reviewer,
                    "latency_ms": attempt.latency_ms,
                })

        if passed:
            return SectionGenerationResult(
                section_id=section_id,
                final_attempt=attempt,
                history=history,
                final_passed_gate=True,
                stop_reason="passed",
            )
        # Diminishing-returns stop: improvement < min_improvement after attempt 2
        if attempt_num >= 2:
            improvement = weighted - previous_score
            if improvement < min_improvement:
                await e("agent_status", agent="orchestrator", status="completed",
                        message=("Diminishing returns "
                                 f"(\u0394{improvement:+.1f}); stopping"),
                        progress=99,
                        data={"section_id": section_id,
                              "stop_reason": "diminishing_returns"})
                return SectionGenerationResult(
                    section_id=section_id,
                    final_attempt=attempt,
                    history=history,
                    final_passed_gate=False,
                    stop_reason="diminishing_returns",
                )
        # Below-gate => signal regeneration before next attempt
        if attempt_num < max_attempts:
            await e("retry", agent="reviewer", status="retrying",
                    message=("Quality below gate \u2014 triggering regeneration "
                             f"(attempt {attempt_num + 1}/{max_attempts})"),
                    data={"section_id": section_id,
                          "attempt": attempt_num,
                          "max_attempts": max_attempts,
                          "score": weighted})
        previous_attempt_text = content_text
        previous_issues = rresult.content.get("ranked_issues") or []
        previous_score = weighted

    return SectionGenerationResult(
        section_id=section_id,
        final_attempt=history[-1],
        history=history,
        final_passed_gate=history[-1].passed_gate,
        stop_reason="max_attempts",
    )


async def predict_grade(
    parsed: dict[str, Any],
    section_reviews: list[dict[str, Any]],
    *,
    emit: Optional[AIMEmitter] = None,
) -> dict[str, Any]:
    e = emit or _noop_emitter
    n = len(section_reviews or [])
    await e("agent_status", agent="grade_predictor", status="running",
            message=f"Predicting final grade across {n} section review(s)",
            progress=10,
            data={"sections_reviewed": n})
    predictor = AIMGradePredictorAgent()
    result = await predictor.run({"parsed": parsed, "section_reviews": section_reviews})
    content = result.content or {}
    predicted = content.get("predicted_grade") or content.get("grade") \
        or content.get("predicted_score")
    await e("agent_status", agent="grade_predictor", status="completed",
            message=(f"Predicted grade: {predicted}" if predicted is not None
                     else "Grade prediction complete"),
            progress=99,
            latency_ms=getattr(result, "latency_ms", 0),
            data={"predicted_grade": predicted,
                  "confidence": content.get("confidence"),
                  "sections_reviewed": n})
    return content


async def fix_section(
    section: dict[str, Any],
    parsed: dict[str, Any],
    draft_content: str,
    *,
    section_id: str | None = None,
    emit: Optional[AIMEmitter] = None,
) -> dict[str, Any]:
    e = emit or _noop_emitter
    section_title = str((section or {}).get("title") or "")
    before_words = len((draft_content or "").split())
    await e("agent_status", agent="fixer", status="running",
            message=f"Diagnosing fixes for {section_title}" if section_title
                    else "Diagnosing fixes",
            progress=10,
            data={"section_id": section_id, "before_words": before_words})
    fixer = AIMFixAgent()
    result = await fixer.run({
        "section_content": draft_content,
        "section_meta": section,
        "parsed": parsed,
    })
    content = result.content or {}
    fixes = (
        content.get("rewrite_suggestions")
        or content.get("fixes")
        or content.get("ranked_issues")
        or []
    )
    fix_count = len(fixes) if isinstance(fixes, list) else 0
    await e("agent_status", agent="fixer", status="completed",
            message=f"Identified {fix_count} fix(es)" if fix_count
                    else "Fix diagnostic complete",
            progress=99,
            latency_ms=getattr(result, "latency_ms", 0),
            data={"section_id": section_id,
                  "fix_count": fix_count,
                  "before_words": before_words})
    return content


__all__ = [
    "AnalysisResult",
    "SectionAttempt",
    "SectionGenerationResult",
    "PASS_THRESHOLD",
    "analyze_assignment",
    "generate_section",
    "predict_grade",
    "fix_section",
]
