"""S17-P2 — AnswerCoach: prep questions + STAR answer scaffolding.

LLM-first with deterministic per-dimension question banks and answer
scaffolds when the AIClient is unavailable or returns an invalid
payload. Output is always coercible into PreparedAnswer / ValuesQuestion.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .schemas import PreparedAnswer, ValueDimension, ValuesQuestion

log = logging.getLogger(__name__)

_QUESTION_BANK: dict[ValueDimension, List[dict[str, Any]]] = {
    "ownership": [
        {
            "q": "Tell me about a project you owned end-to-end. How did you decide what to ship?",
            "why": "Probes whether you drive outcomes vs wait for direction.",
            "listen": ["scope decisions", "trade-offs you made", "who you unblocked"],
        },
    ],
    "collaboration": [
        {
            "q": "Describe a time you partnered with another function to land an outcome neither team could alone.",
            "why": "Tests cross-functional empathy and credit-sharing.",
            "listen": ["partner names", "shared goal", "compromise you made"],
        },
    ],
    "customer_obsession": [
        {
            "q": "Walk me through a decision where you traded internal preference for what the customer needed.",
            "why": "Tests willingness to defend the user against the org.",
            "listen": ["customer signal", "internal pushback", "data you used"],
        },
    ],
    "innovation": [
        {
            "q": "Tell me about a time you proposed an unconventional approach. What happened?",
            "why": "Tests appetite for risk + ability to socialize new ideas.",
            "listen": ["status quo", "your alternative", "outcome"],
        },
    ],
    "execution_speed": [
        {
            "q": "Describe a time you shipped something rough on purpose to learn faster.",
            "why": "Tests bias to ship vs perfectionism.",
            "listen": ["what you cut", "timeline", "what you learned"],
        },
    ],
    "craft_quality": [
        {
            "q": "Tell me about a time you held the line on quality when there was pressure to ship.",
            "why": "Tests standards under deadline pressure.",
            "listen": ["quality issue", "stakeholder pressure", "outcome"],
        },
    ],
    "transparency": [
        {
            "q": "Describe a moment you shared bad news early when it would have been easier to wait.",
            "why": "Tests information hygiene under pressure.",
            "listen": ["what you knew", "who you told", "follow-up plan"],
        },
    ],
    "diversity_inclusion": [
        {
            "q": "Tell me about a time you actively created space for an underheard perspective.",
            "why": "Tests inclusive leadership behavior, not statements.",
            "listen": ["concrete action", "person empowered", "outcome"],
        },
    ],
    "long_term_thinking": [
        {
            "q": "Tell me about a decision you made that paid off only after 12+ months.",
            "why": "Tests appetite for delayed gratification.",
            "listen": ["short-term cost", "long-term thesis", "what you measured"],
        },
    ],
    "frugality": [
        {
            "q": "Describe a time resource constraints made the result better.",
            "why": "Tests creative problem-solving without spend.",
            "listen": ["constraint", "creative move", "outcome vs cost"],
        },
    ],
    "learning_growth": [
        {
            "q": "What's a skill or area you deliberately leveled up in the last 12 months, and how?",
            "why": "Tests self-directed growth posture.",
            "listen": ["specific skill", "method", "evidence of progress"],
        },
    ],
    "wellbeing": [
        {
            "q": "Tell me about a time you protected a teammate's wellbeing under deadline pressure.",
            "why": "Tests sustainable-pace leadership.",
            "listen": ["pressure source", "concrete protection", "outcome"],
        },
    ],
}


def _scaffold_answer(question: str, dim: ValueDimension) -> PreparedAnswer:
    label = dim.replace("_", " ")
    return PreparedAnswer(
        question=question,
        dimension=dim,
        star_situation=(
            "Pick one project from the last 18 months where the "
            f"{label} dimension was at stake. Set context in 2 sentences."
        ),
        star_task=(
            f"State your specific responsibility — what success looked "
            f"like through the lens of {label}."
        ),
        star_action=(
            "Name 2-3 concrete actions you took. Use 'I' not 'we' for the "
            "decision points; quantify scope, timeline, or trade-offs."
        ),
        star_result=(
            "Give one quantified outcome and one second-order impact "
            "(team, customer, downstream metric). Acknowledge what you'd "
            "do differently."
        ),
        talking_points=[
            f"Lead with the {label} stakes — interviewer needs the lens up front.",
            "Name the trade-off explicitly so it lands as a thoughtful choice.",
            "Close with what you learned to signal a growth posture.",
        ],
        pitfalls=[
            "Don't drift into 'we' — they need to hear your contribution.",
            "Don't over-index on outcome; the decision logic is what differentiates.",
            "Avoid generic value words; show, don't claim.",
        ],
    )


class AnswerCoach:
    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self._client = ai_client

    def questions_for(
        self, top_dimensions: List[str], per_dimension: int = 1
    ) -> List[ValuesQuestion]:
        out: List[ValuesQuestion] = []
        for dim in top_dimensions:
            bank = _QUESTION_BANK.get(dim)
            if not bank:
                continue
            for entry in bank[: max(1, per_dimension)]:
                out.append(
                    ValuesQuestion(
                        dimension=dim,
                        question=entry["q"],
                        why_asked=entry["why"],
                        listen_for=list(entry["listen"]),
                    )
                )
        return out

    async def prepare_answers(
        self, questions: List[ValuesQuestion]
    ) -> List[PreparedAnswer]:
        out: List[PreparedAnswer] = []
        for q in questions:
            if self._client is not None:
                try:
                    payload = await self._client.complete_json(
                        prompt=(
                            f"Question: {q.question}\nDimension: {q.dimension}\n"
                            "Return JSON {star_situation, star_task, star_action, "
                            "star_result, talking_points[], pitfalls[]} as STAR "
                            "scaffolding for a candidate."
                        ),
                        system="Return strict JSON only.",
                        schema={
                            "type": "object",
                            "required": [
                                "star_situation", "star_task",
                                "star_action", "star_result",
                            ],
                        },
                        temperature=0.5,
                        task_type="culture_fit_answer",
                    )
                    if (
                        isinstance(payload, dict)
                        and payload.get("star_action")
                        and payload.get("star_result")
                    ):
                        out.append(
                            PreparedAnswer(
                                question=q.question,
                                dimension=q.dimension,
                                star_situation=str(payload.get("star_situation", "")).strip()
                                or _scaffold_answer(q.question, q.dimension).star_situation,
                                star_task=str(payload.get("star_task", "")).strip()
                                or _scaffold_answer(q.question, q.dimension).star_task,
                                star_action=str(payload["star_action"]).strip(),
                                star_result=str(payload["star_result"]).strip(),
                                talking_points=list(payload.get("talking_points") or []) or
                                _scaffold_answer(q.question, q.dimension).talking_points,
                                pitfalls=list(payload.get("pitfalls") or []) or
                                _scaffold_answer(q.question, q.dimension).pitfalls,
                            )
                        )
                        continue
                except Exception as exc:  # noqa: BLE001
                    log.info("answer_coach LLM failed: %s", exc)
            out.append(_scaffold_answer(q.question, q.dimension))
        return out
