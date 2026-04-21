"""Phase D.3 — generate_tailored_personal_statement_variants chain
method + lock_ps_variant endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_engine.chains.document_generator import DocumentGeneratorChain


def _chain(side_effect):
    ai = AsyncMock()
    ai.complete = AsyncMock(side_effect=side_effect)
    return DocumentGeneratorChain(ai), ai


@pytest.mark.asyncio
async def test_ps_variants_default_two() -> None:
    async def fake(**kw):
        if "CONCISE" in kw["prompt"]:
            return "<p>Concise PS</p>"
        if "NARRATIVE" in kw["prompt"]:
            return "<p>Narrative PS</p>"
        return ""

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_personal_statement_variants(
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
async def test_ps_variants_one_failure_isolated() -> None:
    async def fake(**kw):
        if "CONCISE" in kw["prompt"]:
            raise RuntimeError("model down")
        return "narrative body"

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_personal_statement_variants(
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
async def test_ps_variants_explicit_subset() -> None:
    async def fake(**kw):
        return "x"

    chain, _ = _chain(fake)
    out = await chain.generate_tailored_personal_statement_variants(
        user_profile={},
        job_title="t",
        company="c",
        jd_text="",
        gap_analysis={},
        variants=["narrative"],
    )
    assert [v["variant"] for v in out] == ["narrative"]


@pytest.mark.asyncio
async def test_ps_variants_distinct_temperatures() -> None:
    seen_temps = []

    async def fake(**kw):
        seen_temps.append(kw["temperature"])
        return "x"

    chain, _ = _chain(fake)
    await chain.generate_tailored_personal_statement_variants(
        user_profile={},
        job_title="t",
        company="c",
        jd_text="",
        gap_analysis={},
    )
    # Concise uses 0.55, narrative uses 0.75
    assert sorted(seen_temps) == [0.55, 0.75]


# ── Lock endpoint logic ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_ps_endpoint_swaps_locked_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.api.routes.generate import cv_variants as mod
    monkeypatch.setattr("app.core.security.limiter.enabled", False)

    initial = [
        {"variant": "concise", "label": "Concise", "content": "<p>C</p>", "locked": True},
        {"variant": "narrative", "label": "Narrative", "content": "<p>N</p>", "locked": False},
    ]
    state = {
        "row": {
            "id": "app-1",
            "user_id": "user-1",
            "personal_statement_html": "<p>C</p>",
            "ps_variants": initial,
        },
        "patches": [],
    }

    class _Resp:
        def __init__(self, data): self.data = data

    class _Q:
        def __init__(self): self._patch = None
        def select(self, *a, **k): return self
        def update(self, patch):
            self._patch = patch
            return self
        def eq(self, *a, **k): return self
        def maybe_single(self): return self
        def execute(self):
            if self._patch is not None:
                state["row"].update(self._patch)
                state["patches"].append(self._patch)
                return _Resp(state["row"])
            return _Resp(state["row"])

    class _SB:
        def table(self, _name): return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    result = await mod.lock_ps_variant(
        request=None,  # type: ignore[arg-type]
        application_id="app-1",
        variant_key="narrative",
        current_user={"id": "user-1"},
    )
    assert result["lockedVariant"] == "narrative"
    assert result["personalStatementHtml"] == "<p>N</p>"
    locks = {v["variant"]: v["locked"] for v in result["personalStatementVariants"]}
    assert locks == {"concise": False, "narrative": True}
    assert state["patches"][0]["personal_statement_html"] == "<p>N</p>"


@pytest.mark.asyncio
async def test_lock_ps_endpoint_409_when_no_variants(
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
            return _Resp({"id": "app-1", "user_id": "user-1", "ps_variants": []})

    class _SB:
        def table(self, _name): return _Q()

    monkeypatch.setattr(mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(mod, "TABLES", {"applications": "applications"})

    with pytest.raises(HTTPException) as exc:
        await mod.lock_ps_variant(
            request=None,  # type: ignore[arg-type]
            application_id="app-1",
            variant_key="concise",
            current_user={"id": "user-1"},
        )
    assert exc.value.status_code == 409
