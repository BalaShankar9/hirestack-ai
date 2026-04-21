"""Phase D.2 — generate_tailored_cv_variants chain method + lock endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_engine.chains.document_generator import DocumentGeneratorChain


def _chain(side_effect):
    ai = AsyncMock()
    ai.complete = AsyncMock(side_effect=side_effect)
    return DocumentGeneratorChain(ai), ai


@pytest.mark.asyncio
async def test_tailored_variants_default_two() -> None:
    async def fake(**kw):
        if "CONCISE" in kw["prompt"]:
            return "<h1>Concise</h1>"
        if "NARRATIVE" in kw["prompt"]:
            return "<h1>Narrative</h1>"
        return ""

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_cv_variants(
        user_profile={"name": "x"},
        job_title="SWE",
        company="Acme",
        jd_text="python kubernetes",
        gap_analysis={"compatibility_score": 80, "skill_gaps": [], "strengths": []},
        resume_text="resume",
    )
    assert [v["variant"] for v in out] == ["concise", "narrative"]
    assert "Concise" in out[0]["content"]
    assert "Narrative" in out[1]["content"]


@pytest.mark.asyncio
async def test_tailored_variants_explicit_subset() -> None:
    async def fake(**kw):
        return "body"

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        jd_text="",
        gap_analysis={},
        variants=["narrative"],
    )
    assert [v["variant"] for v in out] == ["narrative"]


@pytest.mark.asyncio
async def test_tailored_variants_one_failure_isolated() -> None:
    async def fake(**kw):
        if "CONCISE" in kw["prompt"]:
            raise RuntimeError("model down")
        return "narrative body"

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        jd_text="",
        gap_analysis={},
    )
    by_key = {v["variant"]: v for v in out}
    assert by_key["concise"]["content"] == ""
    assert by_key["narrative"]["content"] == "narrative body"


@pytest.mark.asyncio
async def test_tailored_variants_truncates_long_inputs() -> None:
    captured = []

    async def fake(**kw):
        captured.append(kw["prompt"])
        return "x"

    chain, _ = _chain(fake)
    huge_jd = "kw " * 5000  # well over 4000 chars
    huge_resume = "rs " * 4000
    await chain.generate_tailored_cv_variants(
        user_profile={"k": "v"},
        job_title="t",
        company="c",
        jd_text=huge_jd,
        gap_analysis={},
        resume_text=huge_resume,
        variants=["concise"],
    )
    # one prompt issued and it must be bounded — the caller limits jd to
    # 4000 chars and resume to 3000, so the prompt isn't unbounded
    assert len(captured) == 1
    assert len(captured[0]) < len(huge_jd) + len(huge_resume)


# ── Lock endpoint logic ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_endpoint_swaps_locked_flags_and_cv_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise lock_cv_variant against an in-memory fake supabase."""
    from backend.app.api.routes.generate import cv_variants as mod
    monkeypatch.setattr("app.core.security.limiter.enabled", False)

    initial_variants = [
        {"variant": "concise", "label": "Concise", "content": "<h1>C</h1>", "locked": True},
        {"variant": "narrative", "label": "Narrative", "content": "<h1>N</h1>", "locked": False},
    ]
    state = {
        "row": {
            "id": "app-1",
            "user_id": "user-1",
            "cv_html": "<h1>C</h1>",
            "cv_variants": initial_variants,
        },
        "patches": [],
    }

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Q:
        def __init__(self):
            self._patch = None

        def select(self, *a, **k):
            return self

        def update(self, patch):
            self._patch = patch
            return self

        def eq(self, *a, **k):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            if self._patch is not None:
                state["row"].update(self._patch)
                state["patches"].append(self._patch)
                return _Resp(state["row"])
            return _Resp(state["row"])

    class _SB:
        def table(self, _name):
            return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    result = await mod.lock_cv_variant(
        request=None,  # type: ignore[arg-type]
        application_id="app-1",
        variant_key="narrative",
        current_user={"id": "user-1"},
    )
    assert result["lockedVariant"] == "narrative"
    assert result["cvHtml"] == "<h1>N</h1>"
    locks = {v["variant"]: v["locked"] for v in result["cvVariants"]}
    assert locks == {"concise": False, "narrative": True}
    assert state["patches"][0]["cv_html"] == "<h1>N</h1>"


@pytest.mark.asyncio
async def test_lock_endpoint_404_for_unknown_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from backend.app.api.routes.generate import cv_variants as mod
    monkeypatch.setattr("app.core.security.limiter.enabled", False)

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def maybe_single(self): return self
        def execute(self):
            return _Resp({
                "id": "app-1",
                "user_id": "user-1",
                "cv_html": "x",
                "cv_variants": [{"variant": "concise", "content": "x", "locked": True}],
            })

    class _SB:
        def table(self, _name): return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    with pytest.raises(HTTPException) as exc:
        await mod.lock_cv_variant(
            request=None,  # type: ignore[arg-type]
            application_id="app-1",
            variant_key="bogus",
            current_user={"id": "user-1"},
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_lock_endpoint_409_when_no_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from backend.app.api.routes.generate import cv_variants as mod
    monkeypatch.setattr("app.core.security.limiter.enabled", False)

    class _Resp:
        def __init__(self, data): self.data = data

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def maybe_single(self): return self
        def execute(self):
            return _Resp({"id": "app-1", "user_id": "user-1", "cv_variants": []})

    class _SB:
        def table(self, _name): return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    with pytest.raises(HTTPException) as exc:
        await mod.lock_cv_variant(
            request=None,  # type: ignore[arg-type]
            application_id="app-1",
            variant_key="concise",
            current_user={"id": "user-1"},
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_lock_endpoint_404_when_application_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from backend.app.api.routes.generate import cv_variants as mod
    monkeypatch.setattr("app.core.security.limiter.enabled", False)

    class _Resp:
        def __init__(self, data): self.data = data

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def maybe_single(self): return self
        def execute(self): return _Resp(None)

    class _SB:
        def table(self, _name): return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    with pytest.raises(HTTPException) as exc:
        await mod.lock_cv_variant(
            request=None,  # type: ignore[arg-type]
            application_id="missing",
            variant_key="concise",
            current_user={"id": "user-1"},
        )
    assert exc.value.status_code == 404
