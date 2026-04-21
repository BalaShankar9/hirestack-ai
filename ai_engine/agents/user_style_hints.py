"""Phase C.1 — User style hint synthesis.

Reads agent_memory rows for a user (written by AgentPipeline at the end
of every successful run) and synthesizes a compact `style_preferences`
dict that downstream chains can weave into their prompts.

Design constraints:
- Cold-start safe: returns None when no useful memory exists.
- Conservative: only synthesizes hints from memories with relevance
  ≥ MIN_RELEVANCE and only when at least MIN_RUNS distinct runs back
  the same preference.  A single bad run shouldn't poison the next.
- LLM-friendly: synthesizes plain English directives instead of raw
  metric tuples.  Output is intended to drop straight into a prompt.
- Small surface: a single async function `synthesize_user_style_hints`.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.user_style_hints")

# Only consider memories with at least this much relevance evidence.
# Memories start at 1.0 and drop in 0.15 steps on poor outcomes — 0.55
# is roughly two negative outcomes deep, so anything below has either
# been actively penalised or has zero confirmation.
MIN_RELEVANCE: float = 0.55

# A pattern needs to appear in this many runs before it counts as a
# preference.  Two or more independent runs agreeing > one outlier run.
MIN_RUNS: int = 2

# Cap how many recalled rows we'll synthesize from in a single call.
MAX_MEMORIES: int = 25


async def synthesize_user_style_hints(
    memory: Any,  # AgentMemory
    user_id: str,
    *,
    pipeline_name: str = "cv_generation",
) -> Optional[Dict[str, Any]]:
    """Synthesize a compact style-preferences dict for a user.

    Returns None when there isn't enough signal to make a confident
    recommendation (cold start, fewer than MIN_RUNS confirming runs,
    or all memories filtered out by relevance).
    """
    if not memory or not user_id or user_id == "unknown":
        return None

    try:
        memories = await memory.arecall(user_id, pipeline_name, limit=MAX_MEMORIES)
    except Exception as exc:
        logger.debug("user_style_hints.recall_failed", error=str(exc)[:160])
        return None

    if not memories:
        return None

    # Only trust memories that haven't been actively penalised.
    confirmed = [
        m for m in memories
        if float(m.get("relevance_score") or 0.0) >= MIN_RELEVANCE
    ]
    if len(confirmed) < MIN_RUNS:
        return None

    # ── Aggregate signals from raw memory_value blobs ──────────────────
    # Each memory_value (written by orchestrator.py L1390) looks like:
    #   {
    #     "critic_feedback": {...},
    #     "optimization_patterns": [...],
    #     "fabrication_flags": {...},
    #     "tone": "concise" | "narrative" | "formal",       (optional)
    #     "preferred_keywords": [...],                       (optional)
    #     "avoid_phrases": [...],                            (optional)
    #     "length": "short" | "medium" | "long",             (optional)
    #   }
    # The optional keys don't exist today — they'll start showing up
    # after the orchestrator is taught to capture them. The synthesizer
    # is forward-compatible so adding capture later just lights up more
    # of the output.

    tone_votes: Counter[str] = Counter()
    length_votes: Counter[str] = Counter()
    keyword_votes: Counter[str] = Counter()
    avoid_votes: Counter[str] = Counter()
    optimization_patterns: List[str] = []

    for mem in confirmed:
        value = mem.get("memory_value") or {}
        if not isinstance(value, dict):
            continue

        tone = str(value.get("tone") or "").strip().lower()
        if tone in {"concise", "narrative", "formal", "conversational", "technical"}:
            tone_votes[tone] += 1

        length = str(value.get("length") or "").strip().lower()
        if length in {"short", "medium", "long"}:
            length_votes[length] += 1

        for kw in value.get("preferred_keywords") or []:
            if isinstance(kw, str) and 1 < len(kw) < 40:
                keyword_votes[kw.strip()] += 1

        for phrase in value.get("avoid_phrases") or []:
            if isinstance(phrase, str) and 1 < len(phrase) < 60:
                avoid_votes[phrase.strip()] += 1

        for pattern in value.get("optimization_patterns") or []:
            if isinstance(pattern, str) and len(pattern) < 200:
                optimization_patterns.append(pattern)

    hints: Dict[str, Any] = {}

    # Pick winning tone/length only if it cleared the agreement bar.
    if tone_votes:
        top_tone, count = tone_votes.most_common(1)[0]
        if count >= MIN_RUNS:
            hints["tone"] = top_tone

    if length_votes:
        top_length, count = length_votes.most_common(1)[0]
        if count >= MIN_RUNS:
            hints["length"] = top_length

    # Keep top-N keywords/phrases that earned majority backing.
    confirmed_keywords = [
        kw for kw, count in keyword_votes.most_common(8)
        if count >= MIN_RUNS
    ]
    if confirmed_keywords:
        hints["preferred_keywords"] = confirmed_keywords

    confirmed_avoid = [
        ph for ph, count in avoid_votes.most_common(6)
        if count >= MIN_RUNS
    ]
    if confirmed_avoid:
        hints["avoid_phrases"] = confirmed_avoid

    # Optimization patterns — take 3 most recent unique ones.
    if optimization_patterns:
        seen: set[str] = set()
        recent: List[str] = []
        for pattern in optimization_patterns:
            if pattern not in seen:
                seen.add(pattern)
                recent.append(pattern)
            if len(recent) >= 3:
                break
        if recent:
            hints["recurring_strengths"] = recent

    if not hints:
        return None

    hints["_source"] = {
        "memory_rows_considered": len(confirmed),
        "pipeline": pipeline_name,
    }
    logger.info(
        "user_style_hints.synthesized",
        user_id=user_id,
        keys=sorted(k for k in hints.keys() if not k.startswith("_")),
    )
    return hints


def render_style_hints_for_prompt(hints: Optional[Dict[str, Any]]) -> str:
    """Render style hints as a plain-English block for prompt insertion.

    Returns "" when hints is None/empty so call sites can unconditionally
    interpolate without worrying about extra whitespace.
    """
    if not hints:
        return ""
    lines: List[str] = ["LEARNED USER STYLE PREFERENCES (from prior successful runs):"]
    if tone := hints.get("tone"):
        lines.append(f"- Preferred tone: {tone}")
    if length := hints.get("length"):
        lines.append(f"- Preferred length: {length}")
    if kws := hints.get("preferred_keywords"):
        lines.append(f"- Recurring confirmed keywords to weave in when relevant: {', '.join(kws)}")
    if avoid := hints.get("avoid_phrases"):
        lines.append(f"- Avoid these phrases (user removed them on past runs): {', '.join(avoid)}")
    if strengths := hints.get("recurring_strengths"):
        lines.append("- Recurring strengths to lead with:")
        for s in strengths:
            lines.append(f"  • {s}")
    lines.append("Honor these preferences unless the JD explicitly contradicts them.")
    return "\n".join(lines)
