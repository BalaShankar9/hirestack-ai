"""Tests for batch_jd_fetcher — pure-fn HTML strip + Fetcher glue."""

from __future__ import annotations

import pytest

from app.services.batch_evaluator import BatchEntry
from app.services.batch_jd_fetcher import (
    MAX_OUTPUT_CHARS,
    extract_jd_text,
    make_jd_loader,
)


def _entry(url="https://example.com/job/1") -> BatchEntry:
    return BatchEntry(raw_url=url, canonical_url=url, ats_key=None)


# ── extract_jd_text ─────────────────────────────────────────────────


class TestExtractJdText:
    def test_empty_input(self):
        assert extract_jd_text("") == ""
        assert extract_jd_text(None) == ""  # type: ignore[arg-type]

    def test_plain_text_round_trip(self):
        out = extract_jd_text("Senior Engineer\nWe are hiring.")
        assert "Senior Engineer" in out
        assert "We are hiring." in out

    def test_strips_basic_tags(self):
        out = extract_jd_text("<p>Hello <b>World</b></p>")
        assert "Hello" in out
        assert "World" in out
        assert "<" not in out and ">" not in out

    def test_drops_script_and_content(self):
        html = "<p>Job</p><script>alert('xss');var s=window;</script><p>Desc</p>"
        out = extract_jd_text(html)
        assert "Job" in out
        assert "Desc" in out
        assert "alert" not in out
        assert "window" not in out

    def test_drops_style_block(self):
        html = "<style>.x{color:red}.y{display:none}</style><p>Body</p>"
        out = extract_jd_text(html)
        assert "Body" in out
        assert "color:red" not in out

    def test_drops_chrome_tags(self):
        html = (
            "<header>SiteHeader</header>"
            "<nav>NavLinks</nav>"
            "<main><p>JobDesc</p></main>"
            "<footer>FooterCopy</footer>"
        )
        out = extract_jd_text(html)
        assert "JobDesc" in out
        assert "SiteHeader" not in out
        assert "NavLinks" not in out
        assert "FooterCopy" not in out

    def test_drops_aside_and_form(self):
        html = "<aside>Ad</aside><form>SignupForm</form><p>Body</p>"
        out = extract_jd_text(html)
        assert "Body" in out
        assert "Ad" not in out
        assert "SignupForm" not in out

    def test_drops_svg_iframe(self):
        html = "<svg><circle/></svg><iframe src='x'></iframe><p>Body</p>"
        out = extract_jd_text(html)
        assert "Body" in out

    def test_block_tags_become_newlines(self):
        html = "<p>One</p><p>Two</p><p>Three</p>"
        out = extract_jd_text(html)
        # Each paragraph on its own line.
        lines = out.splitlines()
        assert "One" in lines
        assert "Two" in lines
        assert "Three" in lines

    def test_br_becomes_newline(self):
        html = "Line1<br>Line2<br/>Line3"
        out = extract_jd_text(html)
        lines = out.splitlines()
        assert "Line1" in lines
        assert "Line2" in lines
        assert "Line3" in lines

    def test_list_items_preserved(self):
        html = "<ul><li>Python</li><li>Go</li><li>Rust</li></ul>"
        out = extract_jd_text(html)
        assert "Python" in out
        assert "Go" in out
        assert "Rust" in out

    def test_html_entities_decoded(self):
        out = extract_jd_text("Salary: $100k &amp; up &mdash; equity")
        assert "&amp;" not in out
        assert "&mdash;" not in out
        assert "&" in out and "—" in out

    def test_numeric_entities_decoded(self):
        out = extract_jd_text("Caf&#233;")
        assert "Café" in out

    def test_collapses_whitespace_runs(self):
        out = extract_jd_text("Hello       world\t\t\tagain")
        # Within a line, runs collapse to a single space.
        assert "Hello world again" in out

    def test_drops_blank_lines(self):
        out = extract_jd_text("<p>A</p>\n\n\n<p>B</p>\n\n<p>C</p>")
        for line in out.splitlines():
            assert line.strip(), f"blank line slipped through: {line!r}"

    def test_idempotent_on_already_clean_text(self):
        clean = "Job Title\nResponsibilities\n- Build things\n- Ship things"
        out1 = extract_jd_text(clean)
        out2 = extract_jd_text(out1)
        assert out1 == out2

    def test_truncates_long_output_with_ellipsis(self):
        big = "<p>" + ("hello " * (MAX_OUTPUT_CHARS // 2)) + "</p>"
        out = extract_jd_text(big)
        assert len(out) <= MAX_OUTPUT_CHARS + 1
        assert out.endswith("…")

    def test_short_output_no_ellipsis(self):
        out = extract_jd_text("<p>short</p>")
        assert not out.endswith("…")

    def test_case_insensitive_tag_stripping(self):
        html = "<SCRIPT>evil</SCRIPT><P>Body</P>"
        out = extract_jd_text(html)
        assert "Body" in out
        assert "evil" not in out

    def test_realistic_job_posting(self):
        html = """
        <html><head><script>track();</script><style>.x{}</style></head>
        <body>
          <header><nav>Home | About | Careers</nav></header>
          <main>
            <h1>Senior Backend Engineer</h1>
            <p>We&rsquo;re looking for an experienced engineer to
            join our team.</p>
            <h2>Requirements</h2>
            <ul>
              <li>5+ years Python</li>
              <li>Strong SQL skills</li>
              <li>Distributed systems experience</li>
            </ul>
            <h2>Compensation</h2>
            <p>$150k - $200k &amp; equity</p>
          </main>
          <footer>&copy; 2026 ExampleCo</footer>
        </body></html>
        """
        out = extract_jd_text(html)
        assert "Senior Backend Engineer" in out
        assert "5+ years Python" in out
        assert "Strong SQL skills" in out
        assert "$150k - $200k & equity" in out
        # Chrome stripped.
        assert "track();" not in out
        assert "Home | About | Careers" not in out
        assert "ExampleCo" not in out  # in footer
        # No tags left.
        assert "<" not in out and ">" not in out


# ── make_jd_loader ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loader_fetches_and_strips():
    captured = {}

    async def fetcher(url):
        captured["url"] = url
        return "<p>Hello <b>World</b></p>"

    loader = make_jd_loader(fetcher=fetcher)
    out = await loader(_entry("https://example.com/job/abc"))
    assert "Hello" in out and "World" in out
    assert "<" not in out
    assert captured["url"] == "https://example.com/job/abc"


@pytest.mark.asyncio
async def test_loader_uses_canonical_url_not_raw():
    """If raw_url and canonical_url differ, the loader uses canonical."""
    captured = {}

    async def fetcher(url):
        captured["url"] = url
        return "<p>x</p>"

    loader = make_jd_loader(fetcher=fetcher)
    e = BatchEntry(
        raw_url="https://example.com/job/1?utm_source=spam",
        canonical_url="https://example.com/job/1",
        ats_key=None,
    )
    await loader(e)
    assert captured["url"] == "https://example.com/job/1"


@pytest.mark.asyncio
async def test_loader_raise_propagates():
    """Fetcher errors bubble up; the glue layer catches and tags them."""
    async def fetcher(url):
        raise TimeoutError("slow")

    loader = make_jd_loader(fetcher=fetcher)
    with pytest.raises(TimeoutError):
        await loader(_entry())


@pytest.mark.asyncio
async def test_loader_blank_body_returns_empty():
    async def fetcher(url):
        return ""

    loader = make_jd_loader(fetcher=fetcher)
    assert await loader(_entry()) == ""


@pytest.mark.asyncio
async def test_loader_none_body_returns_empty():
    async def fetcher(url):
        return None  # type: ignore[return-value]

    loader = make_jd_loader(fetcher=fetcher)
    assert await loader(_entry()) == ""


@pytest.mark.asyncio
async def test_loader_pipes_to_glue_correctly():
    """End-to-end: loader output drops into batch_scorer_glue with no surprises."""
    from app.services.batch_scorer_glue import make_llm_scorer

    async def fetcher(url):
        return "<p>Real JD body</p>"

    async def profile_loader(uid):
        return {"title": "Eng"}

    class _AI:
        calls = []
        async def complete_json(self, *, prompt, system=None, max_tokens=1024):
            self.calls.append(prompt)
            return {"match_score": 80}

    ai = _AI()
    scorer = make_llm_scorer(
        user_id="u1",
        profile_loader=profile_loader,
        jd_loader=make_jd_loader(fetcher=fetcher),
        ai_client=ai,
    )
    out = await scorer(_entry())
    assert out.error is None
    assert out.fit_score == pytest.approx(4.0)
    # JD made it into the prompt, stripped.
    assert "Real JD body" in ai.calls[0]
    assert "<p>" not in ai.calls[0]
