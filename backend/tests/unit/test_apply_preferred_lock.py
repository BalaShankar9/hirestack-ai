"""Phase D.5 — _apply_preferred_lock helper unit tests."""
from __future__ import annotations

from app.api.routes.generate.jobs import _apply_preferred_lock


def _v(name: str, locked: bool, content: str = None) -> dict:
    return {
        "variant": name,
        "label": name.title(),
        "content": content if content is not None else f"<{name}/>",
        "locked": locked,
    }


def test_relocks_to_preferred_when_higher_score() -> None:
    variants = [_v("concise", True), _v("narrative", False)]
    scores = {"cv": {"concise": 1.0, "narrative": 4.0}}
    new_canonical = _apply_preferred_lock(variants, scores, "cv")
    assert new_canonical == "<narrative/>"
    assert variants[0]["locked"] is False
    assert variants[1]["locked"] is True


def test_keeps_lock_when_already_preferred() -> None:
    variants = [_v("concise", True), _v("narrative", False)]
    scores = {"cv": {"concise": 5.0, "narrative": 1.0}}
    new_canonical = _apply_preferred_lock(variants, scores, "cv")
    assert new_canonical == "<concise/>"
    assert variants[0]["locked"] is True
    assert variants[1]["locked"] is False


def test_noop_when_scores_missing() -> None:
    variants = [_v("concise", True), _v("narrative", False)]
    new_canonical = _apply_preferred_lock(variants, None, "cv")
    # Returns currently-locked content; flags untouched.
    assert new_canonical == "<concise/>"
    assert variants[0]["locked"] is True
    assert variants[1]["locked"] is False


def test_noop_when_preferred_variant_absent() -> None:
    variants = [_v("concise", True), _v("narrative", False)]
    scores = {"cv": {"executive": 10.0}}
    new_canonical = _apply_preferred_lock(variants, scores, "cv")
    assert new_canonical == "<concise/>"
    assert variants[0]["locked"] is True


def test_noop_when_preferred_variant_empty_content() -> None:
    variants = [_v("concise", True), _v("narrative", False, content="")]
    scores = {"cv": {"narrative": 10.0}}
    new_canonical = _apply_preferred_lock(variants, scores, "cv")
    assert new_canonical == "<concise/>"
    assert variants[0]["locked"] is True


def test_independent_per_document() -> None:
    cv_variants = [_v("concise", True), _v("narrative", False)]
    ps_variants = [_v("concise", True), _v("narrative", False)]
    scores = {
        "cv": {"narrative": 4.0},
        "ps": {"concise": 4.0},
    }
    _apply_preferred_lock(cv_variants, scores, "cv")
    _apply_preferred_lock(ps_variants, scores, "ps")
    assert cv_variants[1]["locked"] is True
    assert ps_variants[0]["locked"] is True


def test_empty_list_returns_empty_string() -> None:
    assert _apply_preferred_lock([], {"cv": {"concise": 1.0}}, "cv") == ""


def test_handles_zero_scores_gracefully() -> None:
    variants = [_v("concise", True), _v("narrative", False)]
    scores = {"cv": {"concise": 0.0, "narrative": 0.0}}
    new_canonical = _apply_preferred_lock(variants, scores, "cv")
    # All-zero scores → preferred_style returns fallback "" → no-op.
    assert new_canonical == "<concise/>"
    assert variants[0]["locked"] is True
