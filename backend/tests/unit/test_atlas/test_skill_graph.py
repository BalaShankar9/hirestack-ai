"""Tests for ATLAS skill graph (Phase 0 foundation)."""
from __future__ import annotations

import pytest

from ai_engine.agents.sub_agents.atlas import skill_graph
from ai_engine.agents.sub_agents.atlas.skill_graph import (
    SkillMatch,
    compute_skill_match,
    reset_model_cache,
    skill_similarity,
)


@pytest.fixture(autouse=True)
def _reset_skill_graph_cache():
    """Ensure each test starts with a clean cache + no leaked model."""
    reset_model_cache()
    yield
    reset_model_cache()


# ─── normalization + identity ─────────────────────────────────────


def test_identical_skills_score_one_via_exact():
    score, source = skill_similarity("Python", "python")
    assert score == 1.0
    assert source == "exact"


def test_normalization_strips_punctuation_but_keeps_plus_hash_dot():
    # "C++" must round-trip and match itself; "C #" → "c#"
    s1, _ = skill_similarity("C++", "c++")
    s2, _ = skill_similarity("C#", "c#")
    s3, _ = skill_similarity(".NET", ".net")
    assert s1 == 1.0
    assert s2 == 1.0
    assert s3 == 1.0


def test_empty_inputs_return_zero():
    assert skill_similarity("", "python")[0] == 0.0
    assert skill_similarity("python", "")[0] == 0.0
    assert skill_similarity(None, None)[0] == 0.0  # type: ignore[arg-type]


# ─── static curated dict ─────────────────────────────────────────


def test_static_pair_javascript_typescript_high():
    score, source = skill_similarity("JavaScript", "TypeScript")
    assert source == "static"
    assert 0.9 <= score <= 1.0


def test_static_pair_is_symmetric():
    s_ab, _ = skill_similarity("AWS", "GCP")
    s_ba, _ = skill_similarity("GCP", "AWS")
    assert s_ab == s_ba > 0.7


def test_static_pair_aws_azure():
    score, source = skill_similarity("AWS", "Azure")
    assert source == "static"
    assert score >= 0.7


# ─── embedding fallback path ─────────────────────────────────────


def test_no_model_falls_back_to_substring(monkeypatch):
    """When sentence-transformers is unavailable, unknown pairs use substring."""
    # Force model load to fail.
    monkeypatch.setattr(skill_graph, "_get_model", lambda: None)
    score, source = skill_similarity("react native", "react")
    # 'react' is substring of 'react native' → length-ratio scaled.
    assert source == "substring"
    assert 0.0 < score < 1.0


def test_no_model_no_overlap_returns_zero(monkeypatch):
    monkeypatch.setattr(skill_graph, "_get_model", lambda: None)
    score, source = skill_similarity("kubernetes", "photoshop")
    assert source == "substring"
    assert score == 0.0


def test_embedding_path_used_when_model_loads(monkeypatch):
    """When a model returns vectors, embedding source is selected."""
    class _FakeModel:
        def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
            # Return vectors that produce cosine ≈ 0.83 between the two.
            # With normalize_embeddings=True, dot product == cosine.
            return [
                [0.9165, 0.4],   # |v|=1 (0.9165^2+0.4^2≈1.0)
                [0.6, 0.8],      # |v|=1
            ]
            # dot = 0.9165*0.6 + 0.4*0.8 = 0.5499 + 0.32 = 0.8699 ≈ 0.87

    monkeypatch.setattr(skill_graph, "_get_model", lambda: _FakeModel())
    score, source = skill_similarity("foobar", "bazquux")
    assert source == "embedding"
    assert 0.8 <= score <= 0.9


def test_embedding_failure_falls_through_to_substring(monkeypatch):
    class _BrokenModel:
        def encode(self, *_, **__):
            raise RuntimeError("CUDA OOM")

    monkeypatch.setattr(skill_graph, "_get_model", lambda: _BrokenModel())
    score, source = skill_similarity("alpha", "beta")
    assert source == "substring"
    assert score == 0.0


# ─── compute_skill_match top-level API ───────────────────────────


def test_compute_skill_match_picks_best_candidate_per_target():
    matches = compute_skill_match(
        candidate_skills=["JavaScript", "Vue"],
        target_skills=["TypeScript", "React"],
    )
    by_target = {m.target_skill: m for m in matches}
    # JS→TS is the best match for TS.
    assert by_target["TypeScript"].candidate_skill == "JavaScript"
    assert by_target["TypeScript"].score >= 0.9
    # Vue→React static pair (0.80) is above default threshold 0.55.
    assert by_target["React"].candidate_skill == "Vue"


def test_compute_skill_match_omits_targets_below_threshold(monkeypatch):
    monkeypatch.setattr(skill_graph, "_get_model", lambda: None)
    matches = compute_skill_match(
        candidate_skills=["photoshop"],
        target_skills=["kubernetes", "terraform"],
    )
    # No overlap → no model → substring all 0.0 → all below threshold.
    assert matches == []


def test_compute_skill_match_handles_empty_inputs():
    assert compute_skill_match([], ["python"]) == []
    assert compute_skill_match(["python"], []) == []
    assert compute_skill_match(None, None) == []  # type: ignore[arg-type]
    assert compute_skill_match(["", "  "], ["python"]) == []


def test_compute_skill_match_threshold_override():
    # With a very high threshold, even good static matches drop.
    matches = compute_skill_match(
        candidate_skills=["AWS"],
        target_skills=["GCP"],
        threshold=0.99,
    )
    assert matches == []


def test_skill_match_to_dict_shape():
    m = SkillMatch(candidate_skill="A", target_skill="B", score=0.123456, source="static")
    assert m.to_dict() == {
        "candidate_skill": "A",
        "target_skill": "B",
        "score": 0.1235,
        "source": "static",
    }


# ─── caching ─────────────────────────────────────────────────────


def test_lru_cache_reuses_results(monkeypatch):
    """Second probe of same pair must not re-call the model."""
    calls = {"n": 0}

    class _CountingModel:
        def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
            calls["n"] += 1
            return [[1.0, 0.0], [0.5, 0.866]]

    monkeypatch.setattr(skill_graph, "_get_model", lambda: _CountingModel())
    skill_similarity("xyz1", "xyz2")
    skill_similarity("xyz1", "xyz2")
    assert calls["n"] == 1
