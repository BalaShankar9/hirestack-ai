# HireStack Virality Playbook — Lessons from Career-Ops

> Companion to [`CAREER_OPS_GAP_ANALYSIS.md`](./CAREER_OPS_GAP_ANALYSIS.md).
> That doc was about feature parity. This one is about **distribution**.
> Date: 2026-05-02.

## Why career-ops went viral (the actual reason)

Stars on a CLI repo don't come from features — they come from **seven overlapping
growth wheels**. Career-ops nails all seven. Listed in order of impact:

| # | Wheel | What it does | Career-ops execution |
|---|---|---|---|
| 1 | **Memetic thesis** | A single tweetable sentence that flips a power dynamic | *"Companies use AI to filter candidates. I just gave candidates AI to choose companies."* |
| 2 | **Founder myth with hard numbers** | Concrete metrics + a hero's-journey arc make it real | *"740 jobs evaluated · 100 CVs · 1 dream role landed → Head of Applied AI"* |
| 3 | **Open-source / shareable substrate** | Stars compound, contributors compound, forks compound | MIT + Star History chart + contrib.rocks badge |
| 4 | **Massive i18n** | 9 README translations = 10× addressable market overnight | EN / ES / DE / FR / PT-BR / KO / JA / ZH-CN / ZH-TW |
| 5 | **Riding adjacent hype waves** | Anchor to the trending platform of the moment | Claude Code → OpenCode → Gemini CLI → Codex |
| 6 | **Public artifacts users want to show off** | Screenshottable outputs become organic ads | A-F scorecards, ATS-CV PDFs, terminal dashboard, demo.gif |
| 7 | **Community + ritual** | Reasons to come back daily and bring friends | Discord + "I got hired" issue template + weekly digest |

**Career-ops has one thing we don't and can't easily copy: it's a CLI repo on
GitHub for the dev tribe.** We're a SaaS for job seekers (a much broader
audience). So we need a SaaS-shaped version of every wheel.

---

## The HireStack Viral Stack — 8 moves, ranked by leverage

### Move 1 — **Ship a free, no-login public tool that embarrasses every competitor**

This is THE single most important thing on this list. Career-ops's equivalent
is *the README itself*; SaaS equivalent is **a public utility URL Google can
index**.

**Build: `hirestack.ai/ghost-check`** — paste any job URL → instant
red/yellow/green verdict + reasoning. No signup. No paywall.

- Reuses our existing `scan_history_service` + adds the `PostingLegitimacyChain`.
- Each scan creates a permanent indexable page: `hirestack.ai/g/<hash>` with the verdict.
- After 6 months the corpus = **tens of thousands of programmatic-SEO pages**
  ranking for *"is [Company] [Role] a ghost job?"*, *"[Company] careers
  legit?"*, *"job posted X days ago still active?"*.
- OG image is dynamically generated: huge red/yellow/green badge + company
  logo + tier + age. Optimized for X / LinkedIn / Reddit screenshots.
- Free tier rate-limit by IP. Logged-in users get full report + "save to my
  pipeline" button. **This is the conversion funnel.**

> Why this wins: Job seekers will *post screenshots of ghost-job verdicts on
> LinkedIn complaining about specific recruiters*. Recruiters will discover
> us by seeing themselves named. Press cycle. Reddit r/recruitinghell loves
> us. We become "the Snopes of job postings."

**Effort:** ~1 week (chain build + public route + OG image generator + SEO).

---

### Move 2 — **A memetic thesis printed on every page**

Career-ops's hero copy is a single role-reversal sentence. Pick ours and
*put it everywhere*: landing hero, X bio, OG image footer, every email.

Candidates for the HireStack thesis:

- *"Recruiters use AI on you. Use AI on them."*
- *"Stop applying to ghost jobs."*
- *"Don't apply to 100 jobs. Apply to the 5 that fit."*
- *"AI-powered candidates. Beats AI-powered ATS."*

**Pick one. Write it like it's a punch line. A/B test if you must, but
commit and repeat it 1,000 times.** Currently our marketing copy is
forgettable feature-listing.

---

### Move 3 — **Make every report a shareable public artifact**

Career-ops users post their A-F scorecards on LinkedIn. We should make
that effortless:

- Every evaluation gets a public-by-default share link `hirestack.ai/r/<slug>`
  the user can flip to private.
- The page is *beautiful* — big score donut, archetype card, Posting
  Legitimacy badge, candidate validation pillars. Looks like a card from
  the Stripe annual letter, not a SaaS dashboard.
- **Dynamic OG image** per report (Vercel `@vercel/og` or Satori): score
  number + role title + verdict. Optimized for LinkedIn 1200×627.
- "Share my evaluation" CTA after every run with one-click LinkedIn / X
  pre-filled post including the URL.

> Side effect: every shared report drives traffic to the `/r/<slug>` page,
> which has "Generate yours" CTA. **Users become unpaid distribution.**

**Effort:** ~3 days.

---

### Move 4 — **Build the dev-tribe ecosystem hook (CLI + extensions)**

Career-ops captured the dev tribe by *being* a CLI tool. We can capture
them by *exposing one*. Three artifacts, all open-source, all promotional:

1. **`npx hirestack eval <url>`** — published npm package. Hits our public
   API, returns Markdown report to terminal. Demo gif on README. Posted
   to HN / r/programming.
2. **VS Code / Cursor extension** — "Evaluate this job posting" command
   from the URL in your clipboard. Tiny webview shows the score. Listed
   in the marketplace = free distribution channel.
3. **Browser extension** — overlay on LinkedIn Jobs / Indeed / Greenhouse
   pages showing **inline trust score + ghost badge** beside every listing.
   This is the unfair-advantage product. People will tweet screenshots of
   "ghost" badges next to specific company logos.

All three are **thin clients to our API**. They cost us almost nothing to
build but multiply our surface area 10×.

**Effort:** CLI ~2 days, VS Code ext ~3 days, browser ext ~1 week.

---

### Move 5 — **Ride the agentic-AI hype wave with first-class integrations**

Career-ops badges Claude Code / OpenCode / Gemini CLI on its README. We
should ship:

- **MCP server** (`@hirestack/mcp`) so Claude Desktop / Cursor / any MCP
  client can call `hirestack.evaluate_job(url)` and `hirestack.cadence_today()`.
- **Custom GPT** + **Claude Skill** in their respective marketplaces. These
  are zero-cost discovery channels with leaderboards.
- **Zapier / Make.com / n8n integrations** — auto-evaluate every URL piped
  in from email/LinkedIn alerts → into your HireStack pipeline. Listed in
  three more marketplaces.

Each marketplace = a separate viral surface. They cost ~1 day each once
the public API is locked.

**Effort:** ~1 week for the trio.

---

### Move 6 — **Daily ritual loop (the morning brief)**

Career-ops's `followup-cadence.mjs` answers *what should I do today?*
We should turn that into a **daily 7am email + web push**:

> *Good morning. Today: 2 follow-ups due (Acme +7d, Beta +3d), 1 ghost job
> in your pipeline (skip Gamma), 3 new high-fit roles on your tracked
> companies (≥4.2). Open dashboard.*

This is the **DAU loop**. Email open rates measure stickiness. Each open
links back to the public report pages → more impressions of our brand.

**Effort:** ~3 days (Postmark / Resend + cron + template).

---

### Move 7 — **i18n the funnel, not just the marketing**

Career-ops translated the README, not the product. **We can do better:**
because every UI string in HireStack flows through known files, we can
produce 9 locales **at LLM build time** with one Makefile target.

- Spanish, Portuguese (BR), German, French, Hindi, Arabic, Korean,
  Japanese, Chinese (Simplified).
- Job seekers in non-English-primary markets are *desperately* underserved
  by US-centric tools (LinkedIn Premium, Teal, Huntr). This is a moat.
- Localize the public ghost-check tool first (highest SEO leverage in
  non-English Google).

**Effort:** ~1 week for tooling + first 3 locales; then ~1 day per locale.

---

### Move 8 — **Founder-myth content + community + Hall of Fame**

Career-ops's hero number is *"740 jobs → 1 dream role"*. We need ours.

- **Pick a real user (or a paid alpha tester)** and document the
  end-to-end. Blog post + 90-second demo video + tweet thread.
- **GitHub `i-got-hired.yml` issue template** equivalent: a `/wins` page
  that any user can submit to. Approved entries become the social proof
  wall on the landing page.
- **Discord** with channels: `#wins`, `#ghost-of-the-week`, `#feedback`,
  `#feature-requests`, `#cv-feedback`.
- **Weekly newsletter** ("HireStack Week"): top 3 ghost jobs detected
  this week (anonymized), a hire story, a product update. Fuels Move 6.

**Effort:** ongoing; ~2 days to set up infra.

---

## What this looks like as a 30-day sprint

| Week | Theme | Ships |
|------|-------|-------|
| 1 | **Soul** — pick the thesis; design the brand voice | Hero copy locked; visual language (terminal-coded, dark, electric); OG image system |
| 2 | **The free utility** | Public ghost-check tool → indexable per-scan pages; dynamic OG images; rate-limited by IP; conversion CTA |
| 3 | **Daily loop + shareable artifacts** | Public share URLs for every report; morning brief email; status taxonomy refactor (T1.D); cadence dashboard (T1.B) |
| 4 | **Distribution surfaces** | `npx hirestack` CLI; MCP server; LinkedIn launch post w/ founder story + first 5 user wins; submit to HN, ProductHunt, r/cscareerquestions |

After Week 4: monthly cadence of (1 marketplace integration + 1 locale +
1 user-win story).

---

## Anti-patterns we must avoid

- **Pricing the ghost-check tool.** It must be free, public, no-login.
  Charging breaks the SEO + share loop. Monetization is "save to pipeline,
  cadence, story bank, batch eval" → those need the account.
- **Walled-garden dashboards.** Every artifact has a public-by-default
  surface. Dashboards should screenshot well.
- **Generic SaaS-y copy** ("Streamline your job search with AI-powered
  insights"). Career-ops doesn't talk like that. We shouldn't either.
- **Too many features before too few users.** We have 90% of the brain.
  We need 10× the surface area.
- **English-only forever.** That ceiling is hit fast.

---

## How this dovetails with the gap analysis (T1/T2 work)

The gap-analysis Tier-1 quartet (T1.A–D) **builds the engine**. This
playbook **builds the megaphone**. They're complementary, not competing:

- T1.A Posting Legitimacy panel → *also* powers the Move 1 public ghost-check.
- T1.B Cadence dashboard → *also* powers the Move 6 morning brief.
- T1.C Pattern insights → *also* powers Move 8 user-win narratives.
- T1.D status taxonomy → prerequisite for both T1.B and Move 6.

**Recommended order of operations:**

1. **Day 1–2:** T1.D status taxonomy + the Move 2 thesis lock.
2. **Day 3–7:** Move 1 — the public ghost-check tool (also builds the
   `PostingLegitimacyChain` that T1.A needs anyway).
3. **Day 8–10:** T1.A Posting Legitimacy panel in the dashboard.
4. **Day 11–14:** T1.B Cadence dashboard + Move 6 morning brief.
5. **Day 15–21:** Move 3 (public share URLs) + Move 4 (`npx hirestack`).
6. **Day 22–30:** Launch — HN, PH, LinkedIn, X, Discord live.

That sequence yields a launch-ready, viral-by-design product in a month
without throwing away any of the T1 engineering.

---

## The one-line summary

> **Career-ops went viral because it was a story you wanted to tell.
> HireStack will go viral when *every output* is a story users want to tell.**
