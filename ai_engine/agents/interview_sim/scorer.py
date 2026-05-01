"""
Answer scorer — STAR structure detection + signal coverage heuristics.

Pure-python; no LLM required. Used by the orchestrator after each
candidate answer to produce an immediate score + feedback bullets.
LLM-driven feedback rewriting is layered on top in the orchestrator.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from ai_engine.agents.interview_sim.schemas import (
    AnswerScore,
    InterviewQuestion,
)


# Words that signal each STAR component.
_SITUATION = ("when", "while at", "at my", "in my role", "the team", "we were",
              "the project", "context", "background")
_TASK = ("my role was", "i was responsible", "i had to", "the goal", "i needed",
         "tasked with", "asked to")
_ACTION = ("i ", "we ", "led", "built", "designed", "drove", "implemented",
           "shipped", "owned", "coordinated", "negotiated", "decided",
           "refactored", "rolled out")
_RESULT = ("resulted", "increased", "decreased", "reduced", "grew", "saved",
           "shipped", "launched", "delivered", "improved", "won", "achieved",
           "%", "x ", "kpi")

_NUMBER_RE = re.compile(r"\b\d[\d,.]*\s*(?:%|x|k|m|b|users?|customers?|qps|"
                        r"requests?|seconds?|days?|weeks?|months?|years?)\b",
                        re.IGNORECASE)


def _hits(text: str, terms) -> int:
    n = 0
    for t in terms:
        if t in text:
            n += 1
    return n


def _star_components(text_lower: str) -> Tuple[float, dict]:
    """Return (score 0-1, dict of component flags)."""
    s = _hits(text_lower, _SITUATION) >= 1
    t = _hits(text_lower, _TASK) >= 1
    a = _hits(text_lower, _ACTION) >= 1
    r = _hits(text_lower, _RESULT) >= 1
    present = sum([s, t, a, r])
    return present / 4.0, {"situation": s, "task": t, "action": a, "result": r}


def _signal_coverage(text_lower: str, question: InterviewQuestion) -> float:
    rubric = [str(x).lower() for x in (question.rubric or []) if x]
    if not rubric:
        # No rubric — fall back to length-based heuristic so we still vary.
        words = len(text_lower.split())
        return min(1.0, words / 120.0)
    hits = 0
    for r in rubric:
        # Match on any meaningful token from the rubric bullet (words ≥ 4 chars).
        tokens = [w for w in re.findall(r"[a-z]{4,}", r)]
        if not tokens:
            continue
        if any(tok in text_lower for tok in tokens):
            hits += 1
    return hits / max(1, len(rubric))


def _clarity(text: str) -> float:
    sents = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sents:
        return 0.0
    avg = sum(len(s.split()) for s in sents) / len(sents)
    # Sweet spot 10-22 words/sentence.
    if 10 <= avg <= 22:
        return 1.0
    if avg < 6 or avg > 40:
        return 0.3
    return 0.7


def _specificity(text: str) -> float:
    nums = len(_NUMBER_RE.findall(text))
    if nums >= 3:
        return 1.0
    if nums == 2:
        return 0.75
    if nums == 1:
        return 0.5
    return 0.2


def score_answer(question: InterviewQuestion, answer: str) -> Tuple[AnswerScore, List[str]]:
    """Return (AnswerScore, feedback bullets)."""
    if not answer or not answer.strip():
        return (
            AnswerScore(star_score=0, signal_coverage=0, clarity=0,
                        specificity=0, overall=0),
            ["Empty answer — try a 60-90 second response using STAR structure."],
        )
    text_lower = answer.lower()
    star, comps = _star_components(text_lower)
    coverage = _signal_coverage(text_lower, question)
    clarity = _clarity(answer)
    specificity = _specificity(answer)
    overall = round(0.30 * star + 0.30 * coverage + 0.20 * clarity + 0.20 * specificity, 3)

    fb: List[str] = []
    if not comps["situation"]:
        fb.append("Set the scene — when and where did this happen?")
    if not comps["task"]:
        fb.append("State your role / what you were responsible for.")
    if not comps["action"]:
        fb.append("Describe what *you* (not the team) actually did.")
    if not comps["result"]:
        fb.append("Close with a measurable outcome (a number, %, or before→after).")
    if specificity < 0.5:
        fb.append("Add at least one quantified detail (numbers carry the answer).")
    if clarity < 0.7:
        fb.append("Tighten sentence length — aim for 10–22 words per sentence.")
    if coverage < 0.5 and question.rubric:
        fb.append(f"Cover the rubric: {', '.join(question.rubric[:3])}.")
    if not fb:
        fb.append("Strong answer — keep this energy.")

    return (
        AnswerScore(
            star_score=round(star, 3),
            signal_coverage=round(coverage, 3),
            clarity=round(clarity, 3),
            specificity=round(specificity, 3),
            overall=overall,
        ),
        fb,
    )
