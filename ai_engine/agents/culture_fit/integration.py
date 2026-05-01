"""S17-P2 — Culture-fit integration: intent + tools + e2e helper."""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

from .answer_coach import AnswerCoach
from .schemas import CultureFitReport
from .signal_extractor import extract_culture_signals
from .values_mapper import ValuesMapper

_INTENT_RE = re.compile(
    r"\b(culture[- ]fit|values|company values|core values|cultural fit)\b"
    r"|\bvalues[- ]based interview\b"
    r"|\bbehavioral interview\b.*\b(values|culture)\b",
    re.IGNORECASE,
)


def detect_culture_fit_intent(text: str) -> Optional[str]:
    if not text:
        return None
    m = _INTENT_RE.search(text)
    return m.group(0) if m else None


async def coach_culture_fit(
    company: str,
    company_text: str,
    candidate_values: Optional[List[str]] = None,
    questions_per_dimension: int = 1,
    top_n: int = 4,
    ai_client: Optional[Any] = None,
) -> CultureFitReport:
    if not company_text or not company_text.strip():
        raise ValueError("company_text must be non-empty")
    started = time.perf_counter()
    signals = extract_culture_signals(company_text)
    mapper = ValuesMapper()
    value_map = mapper.map(signals, company=company, top_n=top_n)
    coach = AnswerCoach(ai_client=ai_client)
    questions = coach.questions_for(
        value_map.top_dimensions, per_dimension=questions_per_dimension
    )
    answers = await coach.prepare_answers(questions)
    risks = mapper.misalignment_risks(value_map, candidate_values)
    return CultureFitReport(
        company=company,
        value_map=value_map,
        questions=questions,
        prepared_answers=answers,
        misalignment_risks=risks,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def _coach_tool(**kwargs: Any) -> Dict[str, Any]:
    report = await coach_culture_fit(
        company=str(kwargs.get("company", "")),
        company_text=str(kwargs.get("company_text", "")),
        candidate_values=kwargs.get("candidate_values"),
        questions_per_dimension=int(kwargs.get("questions_per_dimension", 1)),
        top_n=int(kwargs.get("top_n", 4)),
    )
    return report.model_dump()


def build_culture_fit_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        AgentTool(
            name="coach_culture_fit_interview",
            description=(
                "Extract culture signals from company text and produce "
                "values-based interview questions with STAR scaffolds."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "company_text": {"type": "string"},
                    "candidate_values": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "questions_per_dimension": {"type": "integer"},
                    "top_n": {"type": "integer"},
                },
                "required": ["company_text"],
            },
            fn=_coach_tool,
        )
    )
    return reg
