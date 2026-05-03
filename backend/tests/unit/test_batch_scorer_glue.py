"""Tests for batch_scorer_glue — Scorer factory composing profile+AI+parse."""

from __future__ import annotations

import asyncio

import pytest

from app.services.batch_evaluator import BatchEntry, ScoringResult
from app.services.batch_scorer_glue import make_llm_scorer


# ── helpers ──────────────────────────────────────────────────────────


def _entry(slug: str = "1") -> BatchEntry:
    url = f"https://example.com/job/{slug}"
    return BatchEntry(raw_url=url, canonical_url=url, ats_key=None)


class _StubAI:
    """Configurable AI client stub.

    Pass either ``response`` (echoed each call) or ``side_effect``
    (raised each call).  Records every call for assertions.
    """

    def __init__(self, *, response=None, side_effect=None):
        self._response = response
        self._side_effect = side_effect
        self.calls: list[dict] = []

    async def complete_json(self, *, prompt, system=None, max_tokens=1024):
        self.calls.append(
            {"prompt": prompt, "system": system, "max_tokens": max_tokens}
        )
        if self._side_effect is not None:
            raise self._side_effect
        return self._response


def _ok_profile_loader(profile=None):
    p = profile if profile is not None else {"title": "Eng", "skills": ["Py"]}

    async def _load(user_id):
        return p

    return _load


def _raising_profile_loader(exc: Exception):
    async def _load(user_id):
        raise exc

    return _load


def _ok_jd_loader(text="JD text here"):
    async def _load(entry):
        return text

    return _load


def _raising_jd_loader(exc: Exception):
    async def _load(entry):
        raise exc

    return _load


# ── happy path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_parsed_scoring_result():
    ai = _StubAI(response={"match_score": 80, "title": "Senior Eng", "company": "Acme"})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert isinstance(out, ScoringResult)
    assert out.fit_score == pytest.approx(4.0)
    assert out.error is None
    assert out.title == "Senior Eng"
    assert out.company == "Acme"
    assert len(ai.calls) == 1


@pytest.mark.asyncio
async def test_canonical_url_pinned_even_if_model_lies():
    ai = _StubAI(response={"match_score": 50, "canonical_url": "https://attacker/x"})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    e = _entry("real")
    out = await scorer(e)
    assert out.canonical_url == e.canonical_url


# ── profile loader caching ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_loaded_once_then_cached():
    calls = []

    async def loader(user_id):
        calls.append(user_id)
        return {"title": "X", "skills": ["A"]}

    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=loader,
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    await scorer(_entry("1"))
    await scorer(_entry("2"))
    await scorer(_entry("3"))
    assert calls == ["u1"]  # only loaded once


@pytest.mark.asyncio
async def test_profile_load_failure_surfaces_on_every_entry_no_db_hammering():
    calls = []

    async def loader(user_id):
        calls.append(user_id)
        raise RuntimeError("supabase down")

    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=loader,
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    for slug in ("1", "2", "3"):
        out = await scorer(_entry(slug))
        assert out.error == "profile_load_error:RuntimeError"
        assert out.fit_score is None
    # Loader still only called once even after failure (cache holds the failure).
    assert calls == ["u1"]
    # AI never called when profile failed.
    assert ai.calls == []


@pytest.mark.asyncio
async def test_profile_none_treated_as_empty_not_error():
    """profile_loader returning None is fine — we score with '(no profile on file)'."""
    async def loader(user_id):
        return None

    ai = _StubAI(response={"match_score": 40})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=loader,
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error is None
    assert out.fit_score == pytest.approx(2.0)
    # Prompt should reference the no-profile fallback string.
    assert "(no profile on file)" in ai.calls[0]["prompt"]


# ── JD loader failures ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jd_loader_raise_yields_jd_fetch_error():
    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_raising_jd_loader(TimeoutError("slow")),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "jd_fetch_error:TimeoutError"
    assert out.fit_score is None
    assert ai.calls == []  # AI never called


@pytest.mark.asyncio
async def test_jd_empty_string_yields_jd_empty():
    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(""),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "jd_empty"
    assert ai.calls == []


@pytest.mark.asyncio
async def test_jd_whitespace_only_yields_jd_empty():
    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader("   \n\t  "),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "jd_empty"


@pytest.mark.asyncio
async def test_jd_loader_failure_does_not_cache_across_entries():
    """A JD fetch error for entry A must NOT poison entry B."""
    counter = {"n": 0}

    async def loader(entry):
        counter["n"] += 1
        if entry.canonical_url.endswith("/1"):
            raise RuntimeError("404")
        return "good JD"

    ai = _StubAI(response={"match_score": 60})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=loader,
        ai_client=ai,
    )
    out1 = await scorer(_entry("1"))
    out2 = await scorer(_entry("2"))
    assert out1.error == "jd_fetch_error:RuntimeError"
    assert out2.error is None and out2.fit_score == pytest.approx(3.0)
    assert counter["n"] == 2  # both entries hit the loader


# ── AI call failures ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_raise_yields_ai_error():
    ai = _StubAI(side_effect=ConnectionError("openai down"))
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "ai_error:ConnectionError"
    assert out.fit_score is None


@pytest.mark.asyncio
async def test_ai_returns_junk_yields_parse_error():
    ai = _StubAI(response="not a dict")
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "parse_error"


@pytest.mark.asyncio
async def test_ai_missing_score_yields_parse_error():
    ai = _StubAI(response={"title": "X"})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error == "parse_error"


@pytest.mark.asyncio
async def test_ai_failure_for_one_entry_does_not_affect_others():
    """Per-entry AI failure isolation."""
    n = {"i": 0}

    class _Flaky:
        calls = []

        async def complete_json(self, *, prompt, system=None, max_tokens=1024):
            self.calls.append(prompt)
            n["i"] += 1
            if n["i"] == 1:
                raise RuntimeError("boom")
            return {"match_score": 70}

    ai = _Flaky()
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(),
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    a = await scorer(_entry("1"))
    b = await scorer(_entry("2"))
    assert a.error == "ai_error:RuntimeError"
    assert b.error is None and b.fit_score == pytest.approx(3.5)


# ── prompt assembly wiring ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompt_contains_profile_and_jd_and_url():
    ai = _StubAI(response={"match_score": 50})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=_ok_profile_loader(
            {"title": "PROFILETITLE", "skills": ["SKILLX"]}
        ),
        jd_loader=_ok_jd_loader("JDBODYTEXT"),
        ai_client=ai,
    )
    e = _entry("specific")
    await scorer(e)
    prompt = ai.calls[0]["prompt"]
    assert "PROFILETITLE" in prompt
    assert "SKILLX" in prompt
    assert "JDBODYTEXT" in prompt
    assert e.canonical_url in prompt
    # System prompt is wired through.
    assert ai.calls[0]["system"] is not None
    assert "scoring expert" in ai.calls[0]["system"].lower()


# ── concurrency safety with score_plan ───────────────────────────────


@pytest.mark.asyncio
async def test_works_with_score_plan_concurrent_fanout():
    """Drop the factory output into score_plan and verify it handles parallel calls."""
    from app.services.batch_scorer_worker import score_plan

    calls = []

    async def loader(user_id):
        calls.append("p")
        await asyncio.sleep(0.005)
        return {"title": "T"}

    ai = _StubAI(response={"match_score": 40})
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=loader,
        jd_loader=_ok_jd_loader(),
        ai_client=ai,
    )
    entries = tuple(_entry(str(i)) for i in range(5))
    results = await score_plan(entries, scorer=scorer, concurrency=4)

    assert len(results) == 5
    assert all(r.error is None for r in results)
    assert all(r.fit_score == pytest.approx(2.0) for r in results)
    # Order pinned.
    for i, r in enumerate(results):
        assert r.canonical_url == entries[i].canonical_url
    # Profile loaded only once even under parallel fan-out.
    # (Race window is tiny but guarded by the cache write before await
    # returns; if 5 racers all see _loaded=False, this assertion will
    # legitimately catch that bug.)
    assert calls == ["p"]
