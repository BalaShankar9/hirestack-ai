"""S17-P2 — ValuesMapper: aggregate signals into a culture profile."""
from __future__ import annotations

from typing import List, Optional

from .schemas import CultureSignal, CultureValueMap


class ValuesMapper:
    """Aggregate CultureSignal weights into per-dimension scores."""

    def map(
        self,
        signals: List[CultureSignal],
        company: str = "",
        top_n: int = 4,
    ) -> CultureValueMap:
        scores: dict[str, float] = {}
        for sig in signals:
            scores[sig.dimension] = round(
                scores.get(sig.dimension, 0.0) + float(sig.weight), 3
            )
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top = [d for d, _ in ordered[: max(1, top_n)]]
        return CultureValueMap(
            company=company,
            scores=scores,
            top_dimensions=top,
            signals=signals,
        )

    def misalignment_risks(
        self,
        value_map: CultureValueMap,
        candidate_values: Optional[List[str]] = None,
    ) -> List[str]:
        """Flag company top values not in the candidate's stated values."""
        if not candidate_values:
            return []
        cand = {v.lower().strip() for v in candidate_values if v}
        risks: List[str] = []
        for dim in value_map.top_dimensions:
            if dim.lower() not in cand and dim.replace("_", " ").lower() not in cand:
                risks.append(
                    f"Company emphasizes '{dim.replace('_', ' ')}' but it's "
                    "not on your stated values list — prepare a concrete "
                    "story showing you can operate this way."
                )
        return risks
