"""ATLAS — Semantic skill graph (Phase 0 foundation).

Pure-function semantic matcher. Computes cosine similarity between
candidate-side skills and target-side skills using a local
sentence-transformers model when available, with a curated static
transferability dict as a deterministic fallback.

Hard rules:
  - Zero hard dependency on sentence-transformers. ImportError ⇒
    static fallback. Production path stays usable on bare images.
  - Lazy singleton model (``_get_model``). First call pays the
    ~80MB load; subsequent calls are O(1).
  - All scoring is bounded to [0.0, 1.0]. NaNs ⇒ 0.0.
  - Identical strings (after normalization) always score 1.0.
  - Caches the (a,b) similarity via ``functools.lru_cache(4096)`` so
    repeated probes during fusion are free.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Public types ──────────────────────────────────────────────────


@dataclass
class SkillMatch:
    """One candidate↔target pairing with the score that justified it."""

    candidate_skill: str
    target_skill: str
    score: float  # 0.0 (no overlap) → 1.0 (identical)
    source: str = "embedding"  # "embedding" | "static" | "exact" | "substring"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_skill": self.candidate_skill,
            "target_skill": self.target_skill,
            "score": round(self.score, 4),
            "source": self.source,
        }


# ─── Normalization ─────────────────────────────────────────────────

_NORM_RE = re.compile(r"[^a-z0-9+#.]+")


def _normalize(skill: str) -> str:
    """Lowercase + strip non-token chars. Preserves +, #, . for c++/c#/.net."""
    if not isinstance(skill, str):
        return ""
    return _NORM_RE.sub(" ", skill.lower()).strip()


# ─── Static transferability fallback (~50 curated pairs) ───────────
#
# Ordered (a, b) → score where a / b are normalized. We probe both
# directions so callers don't need to remember canonical ordering.
# Scores are deliberately conservative; tune up as we see real signal.

_STATIC_PAIRS: Dict[Tuple[str, str], float] = {
    # Languages
    ("java", "kotlin"): 0.88,
    ("java", "scala"): 0.82,
    ("java", "typescript"): 0.55,
    ("javascript", "typescript"): 0.95,
    ("python", "ruby"): 0.65,
    ("python", "go"): 0.55,
    ("c++", "rust"): 0.62,
    ("c++", "c"): 0.85,
    ("c#", ".net"): 0.92,
    ("c#", "java"): 0.78,
    ("swift", "objective-c"): 0.80,
    ("swift", "kotlin"): 0.55,
    # FE frameworks
    ("react", "preact"): 0.93,
    ("react", "svelte"): 0.78,
    ("react", "vue"): 0.80,
    ("react", "angular"): 0.65,
    ("vue", "svelte"): 0.75,
    ("nextjs", "remix"): 0.88,
    ("nextjs", "react"): 0.85,
    # BE frameworks
    ("django", "flask"): 0.78,
    ("django", "fastapi"): 0.72,
    ("flask", "fastapi"): 0.82,
    ("express", "fastify"): 0.85,
    ("spring", "spring boot"): 0.95,
    ("rails", "django"): 0.55,
    # Cloud
    ("aws", "gcp"): 0.78,
    ("aws", "azure"): 0.78,
    ("gcp", "azure"): 0.75,
    ("ec2", "compute engine"): 0.88,
    ("s3", "gcs"): 0.92,
    ("s3", "azure blob"): 0.88,
    ("lambda", "cloud functions"): 0.92,
    ("lambda", "azure functions"): 0.92,
    # Data
    ("postgres", "mysql"): 0.82,
    ("postgres", "sqlite"): 0.62,
    ("mongodb", "dynamodb"): 0.55,
    ("mongodb", "couchbase"): 0.78,
    ("redis", "memcached"): 0.85,
    ("kafka", "rabbitmq"): 0.65,
    ("kafka", "kinesis"): 0.78,
    ("snowflake", "bigquery"): 0.85,
    ("snowflake", "redshift"): 0.85,
    # ML
    ("pytorch", "tensorflow"): 0.82,
    ("pytorch", "jax"): 0.72,
    ("scikit-learn", "xgboost"): 0.55,
    ("pandas", "polars"): 0.88,
    ("numpy", "pandas"): 0.55,
    # DevOps
    ("docker", "podman"): 0.92,
    ("kubernetes", "docker swarm"): 0.55,
    ("kubernetes", "nomad"): 0.62,
    ("terraform", "pulumi"): 0.82,
    ("terraform", "cloudformation"): 0.78,
    ("ansible", "chef"): 0.78,
    ("ansible", "puppet"): 0.75,
    ("github actions", "gitlab ci"): 0.88,
    ("jenkins", "github actions"): 0.65,
    # Observability
    ("datadog", "new relic"): 0.85,
    ("grafana", "kibana"): 0.72,
    ("prometheus", "datadog"): 0.55,
}


def _static_score(a: str, b: str) -> Optional[float]:
    if a == b:
        return 1.0
    pair = _STATIC_PAIRS.get((a, b)) or _STATIC_PAIRS.get((b, a))
    return pair


def _substring_score(a: str, b: str) -> float:
    """Cheap last-resort overlap signal (e.g. 'react native' vs 'react')."""
    if not a or not b:
        return 0.0
    if a in b or b in a:
        # Bias by length ratio so 'r' vs 'react native' doesn't score high.
        ratio = min(len(a), len(b)) / max(len(a), len(b))
        return 0.55 * ratio
    return 0.0


# ─── Lazy embedding model singleton ────────────────────────────────

_model_lock = threading.Lock()
_model_state: Dict[str, Any] = {"loaded": False, "model": None}


def _get_model() -> Optional[Any]:
    """Load ``all-MiniLM-L6-v2`` once. ``None`` on any failure."""
    if _model_state["loaded"]:
        return _model_state["model"]
    with _model_lock:
        if _model_state["loaded"]:
            return _model_state["model"]
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            _model_state["model"] = model
            logger.info("atlas.skill_graph loaded sentence-transformers model")
        except Exception as exc:  # noqa: BLE001
            logger.info("atlas.skill_graph embedding model unavailable: %s", exc)
            _model_state["model"] = None
        finally:
            _model_state["loaded"] = True
        return _model_state["model"]


def _embed_pair(model: Any, a: str, b: str) -> Optional[float]:
    """Return cosine similarity in [0,1] or ``None`` if encoding fails."""
    try:
        # encode returns a 2-D array of shape (2, dim) here.
        vecs = model.encode([a, b], show_progress_bar=False, normalize_embeddings=True)
        # Accept numpy arrays, list-of-list, or any 2-row 2-D iterable.
        try:
            v0, v1 = vecs[0], vecs[1]
        except (IndexError, KeyError, TypeError):
            return None
        # With normalize_embeddings=True, dot product == cosine.
        dot = float(sum(float(x) * float(y) for x, y in zip(v0, v1)))
    except Exception as exc:  # noqa: BLE001
        logger.info("atlas.skill_graph embedding encode failed: %s", exc)
        return None
    if math.isnan(dot):
        return 0.0
    # Clamp from cosine [-1,1] into [0,1] (negative ⇒ unrelated).
    return max(0.0, min(1.0, dot))


# ─── Public similarity ─────────────────────────────────────────────


@lru_cache(maxsize=4096)
def _similarity_cached(norm_a: str, norm_b: str) -> Tuple[float, str]:
    """Cached scorer keyed on normalized strings.

    Order of probes:
      1. Exact (after normalization) → 1.0 / "exact"
      2. Static curated dict → score / "static"
      3. Embedding model if loaded → score / "embedding"
      4. Substring fallback → score / "substring"
    """
    if not norm_a or not norm_b:
        return (0.0, "exact")
    if norm_a == norm_b:
        return (1.0, "exact")
    s = _static_score(norm_a, norm_b)
    if s is not None:
        return (s, "static")
    model = _get_model()
    if model is not None:
        emb = _embed_pair(model, norm_a, norm_b)
        if emb is not None:
            return (emb, "embedding")
    return (_substring_score(norm_a, norm_b), "substring")


def skill_similarity(a: str, b: str) -> Tuple[float, str]:
    """Public scorer. Returns (score, source). Safe on any input."""
    return _similarity_cached(_normalize(a), _normalize(b))


# ─── Public top-level API ──────────────────────────────────────────


def compute_skill_match(
    candidate_skills: Iterable[str],
    target_skills: Iterable[str],
    *,
    threshold: float = 0.55,
) -> List[SkillMatch]:
    """For each target skill, return the best candidate match above threshold.

    Each target skill yields at most one ``SkillMatch``. Targets with no
    candidate over ``threshold`` are omitted (callers can compute the
    diff to identify gaps).
    """
    cand = [s for s in (candidate_skills or []) if isinstance(s, str) and s.strip()]
    tgt = [s for s in (target_skills or []) if isinstance(s, str) and s.strip()]
    if not cand or not tgt:
        return []

    matches: List[SkillMatch] = []
    for t in tgt:
        best: Optional[SkillMatch] = None
        for c in cand:
            score, source = skill_similarity(c, t)
            if score < threshold:
                continue
            if best is None or score > best.score:
                best = SkillMatch(
                    candidate_skill=c,
                    target_skill=t,
                    score=score,
                    source=source,
                )
        if best is not None:
            matches.append(best)
    return matches


def reset_model_cache() -> None:
    """Test-only: clear the lazy singleton + lru_cache."""
    with _model_lock:
        _model_state["loaded"] = False
        _model_state["model"] = None
    _similarity_cached.cache_clear()
