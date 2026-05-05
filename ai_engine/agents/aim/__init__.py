"""
AIM — Assignment Intelligence Module agents.

Five Phase-1 agents that turn an academic assignment brief + rubric into
high-precision, rubric-aligned section outputs with a strict quality gate:

    Parser  \u2192 Recon \u2192 Writer \u2192 Reviewer \u2192 GradePredictor

All agents subclass ai_engine.agents.base.BaseAgent so they integrate with
the existing model_router, retry/circuit-breaker, token-streaming sink, and
SSE event emitter.
"""
from ai_engine.agents.aim.parser import AIMParserAgent
from ai_engine.agents.aim.recon import AIMReconAgent
from ai_engine.agents.aim.writer import AIMWriterAgent
from ai_engine.agents.aim.reviewer import AIMReviewerAgent
from ai_engine.agents.aim.grade_predictor import AIMGradePredictorAgent
from ai_engine.agents.aim.fix import AIMFixAgent

__all__ = [
    "AIMParserAgent",
    "AIMReconAgent",
    "AIMWriterAgent",
    "AIMReviewerAgent",
    "AIMGradePredictorAgent",
    "AIMFixAgent",
]
