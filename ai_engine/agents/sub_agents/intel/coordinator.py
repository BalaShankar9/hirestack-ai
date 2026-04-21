"""
IntelCoordinator — orchestrates the full intel sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel): WebsiteIntel, GitHubIntel, CareersIntel, JDIntel, MarketPosition
    → All run simultaneously for maximum speed
  Phase 2 (sequential): CompanyProfile → ApplicationStrategy
    → Profile runs first, then strategy uses profile output

Returns the final merged intel dict compatible with the existing
CompanyIntelChain interface so streaming, storage, and document
generation all work without changes.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, Callable, Awaitable

import structlog

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.intel.website_intel import WebsiteIntelAgent
from ai_engine.agents.sub_agents.intel.github_intel import GitHubIntelAgent
from ai_engine.agents.sub_agents.intel.careers_intel import CareersIntelAgent
from ai_engine.agents.sub_agents.intel.jd_intel import JDIntelAgent
from ai_engine.agents.sub_agents.intel.market_position import MarketPositionAgent
from ai_engine.agents.sub_agents.intel.company_profile import CompanyProfileAgent
from ai_engine.agents.sub_agents.intel.application_strategy import ApplicationStrategyAgent
from ai_engine.agents.sub_agents.intel.evidence_utils import (
    process_evidence,
    summarise_evidence,
)
from ai_engine.agents.tools import (
    trace_start,
    trace_record,
    trace_snapshot,
    get_provider_health_snapshot,
    otel_span,
)
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.coordinator")

IntelEventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class IntelCoordinator:
    """
    Two-phase intel sub-agent coordinator.

    Phase 1 — Parallel data gathering (all at once):
      • WebsiteIntelAgent   — crawls company website pages
      • GitHubIntelAgent    — GitHub org/repo analysis
      • CareersIntelAgent   — careers page + ATS detection
      • JDIntelAgent        — deep JD signal extraction
      • MarketPositionAgent — Glassdoor, LinkedIn, news, competitors, salary

    Phase 2 — LLM synthesis (sequential, after Phase 1 completes):
      • CompanyProfileAgent     — structured company profile
      • ApplicationStrategyAgent — actionable guidance (consumes profile output)

    Returns a merged dict compatible with the legacy CompanyIntelChain output.
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    # Fields we expect a well-formed CompanyProfileAgent output to carry.
    # Missing / empty ones are surfaced in the profile_schema_audit so the
    # frontend can show a "partial intel" badge rather than a confident-looking
    # but hollow profile.
    _EXPECTED_PROFILE_FIELDS: tuple[str, ...] = (
        "industry",
        "stage",          # early / growth / public / …
        "headcount",
        "tech_stack",
        "leadership",
        "mission",
        "culture_values",
        "recent_news",
        "funding",
    )

    @staticmethod
    def _audit_profile_schema(profile: dict) -> list[str]:
        """
        Return the list of expected fields that are empty in the final profile.
        'Empty' means None, '', [], {}, 0, or False.
        """
        missing: list[str] = []
        for field in IntelCoordinator._EXPECTED_PROFILE_FIELDS:
            v = profile.get(field)
            if v in (None, "", [], {}, 0, False):
                missing.append(field)
        return missing

    async def gather_intel(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        company_url: Optional[str] = None,
        on_event: Optional[IntelEventCallback] = None,
    ) -> dict[str, Any]:
        """Full multi-agent intel gathering with two-phase execution."""
        start = time.monotonic()
        trace_start()
        trace_record({
            "kind": "pipeline_start",
            "company": company[:80],
            "job_title": job_title[:80],
        })

        if on_event:
            await self._emit(on_event, f"Intel swarm deploying 5 sub-agents for {company}…", "running", "recon")

        # Build shared context for all agents
        base_context: dict[str, Any] = {
            "company": company,
            "company_name": company,
            "company_url": company_url,
            "job_title": job_title,
            "jd_text": jd_text,
            "on_event": on_event,
        }

        # ── PHASE 1: Parallel data gathering ──────────────────────
        phase1_agents = [
            WebsiteIntelAgent(ai_client=self.ai_client),
            GitHubIntelAgent(ai_client=self.ai_client),
            CareersIntelAgent(ai_client=self.ai_client),
            JDIntelAgent(ai_client=self.ai_client),
            MarketPositionAgent(ai_client=self.ai_client),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            with otel_span("intel.phase1", agents=",".join(a.name for a in phase1_agents)):
                phase1_results = await asyncio.wait_for(
                    coordinator.gather(base_context),
                    timeout=20,
                )
        except asyncio.TimeoutError:
            logger.warning("intel_phase1_timeout", agents=[a.name for a in phase1_agents])
            # Return empty results for timed-out agents
            phase1_results = [
                SubAgentResult(agent_name=a.name, error="Phase 1 timeout (20s)")
                for a in phase1_agents
            ]

        # Collect results by agent name
        raw_intel: dict[str, dict] = {}
        all_evidence: list[dict] = []
        data_sources: list[str] = []
        agent_latencies: dict[str, int] = {}

        for result in phase1_results:
            agent_latencies[result.agent_name] = result.latency_ms
            trace_record({
                "kind": "sub_agent",
                "phase": "phase1",
                "agent": result.agent_name,
                "ok": bool(result.ok),
                "latency_ms": result.latency_ms,
                "confidence": round(float(result.confidence or 0), 2),
                "evidence_items": len(result.evidence_items or []),
                "error": (result.error or "")[:160] if not result.ok else None,
            })
            if result.ok:
                raw_intel[result.agent_name] = result.data
                all_evidence.extend(result.evidence_items)
                # Track which sources actually provided data
                if result.data and result.confidence > 0.2:
                    data_sources.append(result.agent_name)
            else:
                logger.warning("intel_agent_failed", agent=result.agent_name, error=result.error)
                raw_intel[result.agent_name] = {"error": result.error}

        phase1_time = time.monotonic() - start

        # ── PHASE 1.5: Deep-crawl top-up ──────────────────────────
        # If Phase 1 returned very fast (no search API keys, most sources empty),
        # invest the remaining budget in targeted web queries instead of giving
        # the user a 2-second "completed" that is actually empty.
        MIN_BUDGET_S = float(__import__("os").getenv("RECON_MIN_BUDGET_S", "10"))
        if phase1_time < MIN_BUDGET_S and len(data_sources) < 3:
            remaining = MIN_BUDGET_S - phase1_time
            if on_event:
                await self._emit(
                    on_event,
                    f"Phase 1 finished in {phase1_time:.1f}s with {len(data_sources)}/5 sources — investing {remaining:.0f}s in deep web queries.",
                    "running", "analysis",
                    metadata={"remaining_budget_s": round(remaining, 1)},
                )
            try:
                extra_evidence, extra_sources = await asyncio.wait_for(
                    self._deep_web_topup(company, job_title, on_event),
                    timeout=remaining,
                )
                all_evidence.extend(extra_evidence)
                for s in extra_sources:
                    if s not in data_sources:
                        data_sources.append(s)
                # Attach raw topup results so downstream synthesis can use them
                raw_intel.setdefault("deep_web", {})
                raw_intel["deep_web"] = {"evidence_count": len(extra_evidence), "sources": extra_sources}
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.warning("deep_web_topup_failed", error=str(e))

        phase1_total_time = time.monotonic() - start

        if on_event:
            source_count = len(data_sources)
            await self._emit(
                on_event,
                f"Phase 1 complete: {source_count}/5 agents returned data in {phase1_total_time:.1f}s. Running synthesis…",
                "running", "analysis",
                metadata={
                    "sources": data_sources,
                    "latencies": agent_latencies,
                    "phase1_seconds": round(phase1_total_time, 1),
                    "phase1_raw_seconds": round(phase1_time, 1),
                },
            )

        # ── Evidence post-processing before synthesis ─────────────
        # Dedup near-duplicates, cap per-source, rank by tier/recency/credibility.
        # Keeps the LLM prompt tight and prevents one noisy source from
        # dominating. Summary logged for observability; raw evidence kept
        # (synthesis uses processed, downstream recon_refine uses processed).
        evidence_before = len(all_evidence)
        processed_evidence = process_evidence(
            all_evidence,
            max_total=int(__import__("os").getenv("RECON_MAX_EVIDENCE", "60")),
            max_per_source=int(__import__("os").getenv("RECON_MAX_PER_SOURCE", "8")),
        )
        evidence_summary = summarise_evidence(processed_evidence)
        trace_record({
            "kind": "evidence_processed",
            "before": evidence_before,
            "after": len(processed_evidence),
            "summary": evidence_summary,
        })
        if on_event and evidence_before != len(processed_evidence):
            await self._emit(
                on_event,
                f"Evidence curated: {evidence_before} → {len(processed_evidence)} items "
                f"({evidence_summary.get('total_duplicates_folded', 0)} duplicates folded).",
                "running", "analysis",
                metadata={"evidence_summary": evidence_summary},
            )
        # Swap curated evidence into the pool the synthesis agents see.
        all_evidence = processed_evidence

        # ── PHASE 2a: Company Profile synthesis ────────────────────
        synthesis_context = {
            **base_context,
            "raw_intel": raw_intel,
        }

        profile_agent = CompanyProfileAgent(ai_client=self.ai_client)
        with otel_span("intel.phase2.company_profile"):
            profile_result = await profile_agent.safe_run(synthesis_context)
        trace_record({
            "kind": "sub_agent",
            "phase": "phase2a",
            "agent": profile_result.agent_name,
            "ok": bool(profile_result.ok),
            "latency_ms": profile_result.latency_ms,
        })

        # ── PHASE 2b: Application Strategy (needs profile output) ─────
        # Strategy agent reads the company profile, so it must run AFTER
        # CompanyProfileAgent completes — NOT in parallel.
        if profile_result.ok:
            raw_intel["company_profile"] = profile_result.data
        strategy_context = {
            **base_context,
            "raw_intel": raw_intel,
        }
        strategy_agent = ApplicationStrategyAgent(ai_client=self.ai_client)
        with otel_span("intel.phase2.application_strategy"):
            strategy_result = await strategy_agent.safe_run(strategy_context)
        trace_record({
            "kind": "sub_agent",
            "phase": "phase2b",
            "agent": strategy_result.agent_name,
            "ok": bool(strategy_result.ok),
            "latency_ms": strategy_result.latency_ms,
        })

        agent_latencies[profile_result.agent_name] = profile_result.latency_ms
        agent_latencies[strategy_result.agent_name] = strategy_result.latency_ms

        if profile_result.ok:
            all_evidence.extend(profile_result.evidence_items)
        if strategy_result.ok:
            all_evidence.extend(strategy_result.evidence_items)

        # ── PHASE 3: Recon Critic — gap detection + targeted re-fire ──
        # After synthesis we know which dimensions the LLMs were able to fill
        # from the evidence we gave them. If the profile has obvious holes
        # (no funding_stage, no leadership, no recent news, no tech stack),
        # we fire one more round of highly targeted queries aimed at those
        # specific gaps and let the next Phase re-synthesis pick them up.
        critic_enabled = __import__("os").getenv("RECON_CRITIC_ENABLED", "1").lower() not in ("0", "false", "no")
        critic_budget_s = float(__import__("os").getenv("RECON_CRITIC_BUDGET_S", "8"))
        if critic_enabled and profile_result.ok and critic_budget_s > 0:
            profile_data = profile_result.data or {}
            gaps = self._detect_gaps(profile_data, all_evidence)
            if gaps:
                if on_event:
                    await self._emit(
                        on_event,
                        f"Recon critic found {len(gaps)} gap(s): {', '.join(gaps)}. Firing targeted queries.",
                        "running", "analysis",
                        metadata={"gaps": gaps},
                    )
                try:
                    extra_evidence, extra_sources = await asyncio.wait_for(
                        self._close_gaps(company, job_title, gaps, on_event),
                        timeout=critic_budget_s,
                    )
                    all_evidence.extend(extra_evidence)
                    for s in extra_sources:
                        if s not in data_sources:
                            data_sources.append(s)
                    raw_intel["recon_critic"] = {
                        "gaps_detected": gaps,
                        "gap_evidence_count": len(extra_evidence),
                        "gap_sources": extra_sources,
                    }
                except asyncio.TimeoutError:
                    raw_intel["recon_critic"] = {"gaps_detected": gaps, "status": "timeout"}
                except Exception as e:
                    logger.warning("recon_critic_failed", error=str(e))
                    raw_intel["recon_critic"] = {"gaps_detected": gaps, "error": str(e)[:200]}
            else:
                raw_intel["recon_critic"] = {"gaps_detected": [], "status": "clean"}

        # ── PHASE 3.5: Refine profile with gap-closing evidence ───────
        # When the critic successfully closed ≥3 new evidence items, re-run
        # the CompanyProfileAgent ONCE with the enriched evidence pool.
        # Strategy is NOT re-run — it's the expensive agent and profile is
        # what the user sees first. Gated by RECON_REFINE_ENABLED (default on)
        # and RECON_REFINE_BUDGET_S (default 10s).
        refine_enabled = __import__("os").getenv("RECON_REFINE_ENABLED", "1").lower() not in ("0", "false", "no")
        refine_budget_s = float(__import__("os").getenv("RECON_REFINE_BUDGET_S", "10"))
        critic_meta = raw_intel.get("recon_critic") or {}
        extra_count = int(critic_meta.get("gap_evidence_count") or 0)
        if (
            refine_enabled
            and profile_result.ok
            and extra_count >= 3
            and refine_budget_s > 0
        ):
            if on_event:
                await self._emit(
                    on_event,
                    f"Refining profile with {extra_count} gap-closing evidence items…",
                    "running", "analysis",
                    metadata={"extra_evidence": extra_count},
                )
            try:
                refine_context = {
                    **base_context,
                    "raw_intel": raw_intel,  # includes recon_critic + critic evidence sources
                    "prior_profile": profile_result.data,
                    "gap_evidence": [
                        e for e in all_evidence
                        if (e.get("sub_agent") == "recon_critic")
                    ][:20],
                }
                refined_agent = CompanyProfileAgent(ai_client=self.ai_client)
                refined_result = await asyncio.wait_for(
                    refined_agent.safe_run(refine_context),
                    timeout=refine_budget_s,
                )
                if refined_result.ok and refined_result.data:
                    # Merge only NEW / non-empty fields from the refined profile
                    # into the original — don't overwrite fields the first pass
                    # already filled with equivalent content.
                    original = profile_result.data or {}
                    refined = refined_result.data or {}
                    merged_profile = dict(original)
                    fields_updated: list[str] = []
                    for k, v in refined.items():
                        if v in (None, "", [], {}, 0, False):
                            continue
                        existing = original.get(k)
                        # Replace empty/missing values; for lists prefer the
                        # longer one (more evidence consumed).
                        if existing in (None, "", [], {}, 0, False):
                            merged_profile[k] = v
                            fields_updated.append(k)
                        elif isinstance(existing, list) and isinstance(v, list) and len(v) > len(existing):
                            merged_profile[k] = v
                            fields_updated.append(k)
                        elif isinstance(existing, str) and isinstance(v, str) and len(v) > len(existing) * 1.3:
                            merged_profile[k] = v
                            fields_updated.append(k)
                    if fields_updated:
                        profile_result.data = merged_profile
                        raw_intel["company_profile"] = merged_profile
                        # Carry refined evidence through so it shows up downstream
                        if refined_result.evidence_items:
                            all_evidence.extend(refined_result.evidence_items)
                        raw_intel["recon_refine"] = {
                            "status": "applied",
                            "fields_updated": fields_updated,
                            "latency_ms": refined_result.latency_ms,
                        }
                        agent_latencies[f"{refined_result.agent_name}_refine"] = refined_result.latency_ms
                        if on_event:
                            await self._emit(
                                on_event,
                                f"Profile refined: updated {', '.join(fields_updated[:6])}.",
                                "completed", "analysis",
                                metadata={"fields_updated": fields_updated},
                            )
                    else:
                        raw_intel["recon_refine"] = {"status": "no_improvement"}
                else:
                    raw_intel["recon_refine"] = {
                        "status": "failed",
                        "error": (refined_result.error or "")[:200],
                    }
            except asyncio.TimeoutError:
                raw_intel["recon_refine"] = {"status": "timeout"}
            except Exception as e:
                logger.warning("recon_refine_failed", error=str(e))
                raw_intel["recon_refine"] = {"status": "error", "error": str(e)[:200]}

        # ── Profile schema sanity check ───────────────────────────
        # Lightweight post-synthesis audit: which expected fields did the
        # profile end up with? If any critical ones are empty, surface it
        # in raw_intel so downstream UI / eval can flag it. No blocking.
        profile_data_final = profile_result.data or {} if profile_result.ok else {}
        missing_fields = self._audit_profile_schema(profile_data_final)
        raw_intel["profile_schema_audit"] = {
            "total_expected": len(self._EXPECTED_PROFILE_FIELDS),
            "missing": missing_fields,
            "complete_pct": round(
                100.0 * (len(self._EXPECTED_PROFILE_FIELDS) - len(missing_fields))
                / max(1, len(self._EXPECTED_PROFILE_FIELDS)),
                1,
            ),
        }
        if missing_fields and on_event:
            await self._emit(
                on_event,
                f"Profile audit: {len(missing_fields)} field(s) still empty ({', '.join(missing_fields[:4])}"
                + ("…" if len(missing_fields) > 4 else "") + ").",
                "running", "analysis",
                metadata={"missing_fields": missing_fields},
            )

        # Provider health snapshot (useful for cost / reliability dashboards)
        raw_intel["provider_health"] = get_provider_health_snapshot()

        total_time = time.monotonic() - start
        trace_record({
            "kind": "pipeline_end",
            "total_seconds": round(total_time, 2),
            "evidence_count": len(all_evidence),
            "data_sources": list(data_sources),
            "profile_ok": bool(profile_result.ok),
            "strategy_ok": bool(strategy_result.ok),
            "missing_profile_fields": missing_fields,
        })
        raw_intel["trace"] = trace_snapshot()

        # ── MERGE into legacy-compatible format ───────────────────
        merged = self._merge_results(
            company=company,
            raw_intel=raw_intel,
            profile=profile_result.data if profile_result.ok else {},
            strategy=strategy_result.data if strategy_result.ok else {},
            data_sources=data_sources,
            all_evidence=all_evidence,
            agent_latencies=agent_latencies,
            total_time_s=total_time,
        )

        if on_event:
            await self._emit(
                on_event,
                f"Intel complete: {len(data_sources)} sources, {len(all_evidence)} evidence items, {merged['confidence']} confidence ({total_time:.1f}s).",
                "completed", "recon",
                metadata={
                    "confidence": merged["confidence"],
                    "data_sources": merged["data_sources"],
                    "evidence_count": len(all_evidence),
                    "total_seconds": round(total_time, 1),
                    "agent_latencies": agent_latencies,
                },
            )

        return merged

    async def _deep_web_topup(
        self,
        company: str,
        job_title: str,
        on_event: Optional[IntelEventCallback],
    ) -> tuple[list[dict], list[str]]:
        """
        Fire a handful of targeted web queries to add verifiable evidence when
        Phase 1 came back thin. Uses the multi-provider `_web_search` which
        falls back to DuckDuckGo HTML + Wikipedia when no API keys are set,
        so this works even in zero-config deployments.

        Returns (evidence_items, source_labels).
        """
        try:
            from ai_engine.agents.tools import _web_search
        except Exception:
            return [], []

        queries: list[tuple[str, str]] = [
            ("overview", f"{company} company overview what does it do"),
            ("funding", f"{company} funding investors headcount employees"),
            ("culture", f"{company} culture values employees reviews"),
            ("recent", f"{company} news 2025 2026"),
            ("glassdoor", f"site:glassdoor.com {company} reviews"),
            ("indeed", f"site:indeed.com {company} reviews"),
            ("trustpilot", f"site:trustpilot.com {company}"),
        ]
        if job_title:
            queries.append(("hiring", f"{company} {job_title} hiring team"))
            queries.append(("interview", f"{company} {job_title} interview process"))
            queries.append(("levels", f"site:levels.fyi {company} {job_title}"))

        async def _one(label: str, q: str) -> tuple[str, dict]:
            try:
                return label, await _web_search(q, max_results=4)
            except Exception as e:
                return label, {"results": [], "error": str(e)[:200]}

        results = await asyncio.gather(*[_one(label, q) for label, q in queries], return_exceptions=False)

        evidence: list[dict] = []
        sources: list[str] = []
        for label, payload in results:
            provider = payload.get("provider") or "unknown"
            hits = payload.get("results") or []
            if not hits:
                continue
            sources.append(f"web:{label}")
            for item in hits[:3]:
                snippet = item.get("snippet") or item.get("title") or ""
                link = item.get("link") or ""
                if not snippet:
                    continue
                evidence.append({
                    "fact": f"[{label}] {snippet[:350]}",
                    "source": link or f"search:{provider}:{label}",
                    "tier": "DERIVED",
                    "sub_agent": "deep_web",
                    "provider": provider,
                })
            if on_event:
                try:
                    await self._emit(
                        on_event,
                        f"Deep-web [{label}] via {provider}: {len(hits)} result(s).",
                        "running", "analysis",
                        metadata={"provider": provider, "count": len(hits)},
                    )
                except Exception:
                    pass

        return evidence, sources

    # ── Recon Critic helpers ──────────────────────────────────────────

    # Map of gap-name → (check_fn, list of query templates).
    # check_fn receives (profile_dict, evidence_list) and returns True when
    # that dimension is missing or very thin.
    @staticmethod
    def _detect_gaps(profile: dict, evidence: list[dict]) -> list[str]:
        """
        Deterministic gap analyser. Returns the list of dimension labels
        that the synthesis output is missing, ordered by priority.

        A gap is flagged when the relevant profile field is empty/short AND
        no evidence item mentions the dimension keyword. Evidence matching
        is intentionally generous — if we even have a breadcrumb we skip
        the dimension to avoid duplicate traffic.
        """
        if not isinstance(profile, dict):
            return []

        def _profile_has(keys: tuple[str, ...]) -> bool:
            for k in keys:
                v = profile.get(k)
                if isinstance(v, str) and v.strip():
                    return True
                if isinstance(v, (list, dict)) and len(v) > 0:
                    return True
                if v not in (None, "", 0, False):
                    return True
            return False

        def _evidence_mentions(words: tuple[str, ...]) -> bool:
            for item in evidence:
                blob = (
                    (item.get("fact") or "") + " "
                    + (item.get("source") or "")
                ).lower()
                if any(w in blob for w in words):
                    return True
            return False

        gaps: list[str] = []

        # 1. Funding / financial stage
        if not _profile_has(("funding_stage", "funding", "financials")) and \
           not _evidence_mentions(("funding", "raised", "investor", "series ", "seed ", "valuation")):
            gaps.append("funding")

        # 2. Leadership
        if not _profile_has(("leadership", "executives", "founders", "ceo")) and \
           not _evidence_mentions(("ceo", "founder", "co-founder", "cto", "president", "leadership")):
            gaps.append("leadership")

        # 3. Recent news / momentum
        if not _profile_has(("recent_news", "news", "momentum")) and \
           not _evidence_mentions(("announced", "launched", "acquired", "partnership", "press release")):
            gaps.append("recent_news")

        # 4. Tech stack
        if not _profile_has(("tech_stack", "technologies", "stack")) and \
           not _evidence_mentions(("python", "java", "typescript", "react", "kubernetes", "aws", "postgres", "stack")):
            gaps.append("tech_stack")

        # 5. Culture / values
        if not _profile_has(("culture", "values", "mission")) and \
           not _evidence_mentions(("culture", "values", "mission", "remote", "benefits")):
            gaps.append("culture")

        # 6. Headcount / size
        if not _profile_has(("headcount", "employees", "size")) and \
           not _evidence_mentions(("employees", "headcount", "team size", "people work")):
            gaps.append("headcount")

        return gaps

    async def _close_gaps(
        self,
        company: str,
        job_title: str,
        gaps: list[str],
        on_event: Optional[IntelEventCallback],
    ) -> tuple[list[dict], list[str]]:
        """
        Fire a small, highly targeted query set for each detected gap and
        return new evidence items tagged with `sub_agent="recon_critic"`.

        Each gap gets 1–2 queries (not 4+ like the generic topup) because
        we already did the broad sweep in Phase 1.5. Runs the queries in
        parallel across gaps.
        """
        try:
            from ai_engine.agents.tools import _web_search
        except Exception:
            return [], []

        GAP_QUERIES: dict[str, list[str]] = {
            "funding": [
                f"{company} funding round series valuation site:techcrunch.com OR site:bloomberg.com",
                f"{company} investors total funding raised crunchbase",
            ],
            "leadership": [
                f"{company} CEO founder leadership team",
                f'"{company}" executive team linkedin',
            ],
            "recent_news": [
                f"{company} news 2026",
                f"{company} announcement press release 2025",
            ],
            "tech_stack": [
                f"{company} engineering blog tech stack",
                f"{company} {job_title} technologies used" if job_title else f"{company} technologies stack",
            ],
            "culture": [
                f"{company} company culture values mission",
                f"{company} employee reviews benefits remote",
            ],
            "headcount": [
                f"{company} number of employees headcount company size",
            ],
        }

        tasks: list[tuple[str, str, Any]] = []
        for gap in gaps:
            for q in GAP_QUERIES.get(gap, []):
                tasks.append((gap, q, _web_search(q, max_results=3)))

        if not tasks:
            return [], []

        coros = [t[2] for t in tasks]
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        evidence: list[dict] = []
        sources: list[str] = []
        per_gap_counts: dict[str, int] = {}

        for (gap, query, _), res in zip(tasks, raw_results):
            if isinstance(res, Exception):
                continue
            hits = res.get("results") or []
            if not hits:
                continue
            provider = res.get("provider") or "unknown"
            sources.append(f"critic:{gap}")
            per_gap_counts[gap] = per_gap_counts.get(gap, 0) + len(hits)
            for item in hits[:3]:
                snippet = item.get("snippet") or item.get("title") or ""
                link = item.get("link") or ""
                if not snippet:
                    continue
                evidence.append({
                    "fact": f"[gap:{gap}] {snippet[:350]}",
                    "source": link or f"critic:{provider}:{gap}",
                    "tier": "DERIVED",
                    "sub_agent": "recon_critic",
                    "gap": gap,
                    "provider": provider,
                })

        if on_event and per_gap_counts:
            try:
                await self._emit(
                    on_event,
                    "Critic closed gaps: " + ", ".join(f"{g}={c}" for g, c in per_gap_counts.items()),
                    "running", "analysis",
                    metadata={"gap_counts": per_gap_counts},
                )
            except Exception:
                pass

        return evidence, sources

    def _merge_results(
        self,
        company: str,
        raw_intel: dict[str, dict],
        profile: dict,
        strategy: dict,
        data_sources: list[str],
        all_evidence: list[dict],
        agent_latencies: dict[str, int],
        total_time_s: float,
    ) -> dict[str, Any]:
        """Merge all sub-agent data into the legacy CompanyIntelChain output format."""

        jd = raw_intel.get("jd_intel", {})
        website = raw_intel.get("website_intel", {})
        github = raw_intel.get("github_intel", {})
        careers = raw_intel.get("careers_intel", {})
        market = raw_intel.get("market_position", {})

        # Use profile (LLM-synthesized) as the base, then enrich with raw data
        result: dict[str, Any] = {}

        # Company overview
        result["company_overview"] = profile.get("company_overview", {})
        if not result["company_overview"]:
            result["company_overview"] = {"name": company}
        result["company_overview"].setdefault("name", company)
        if website.get("base_url"):
            result["company_overview"]["website"] = website["base_url"]

        # Culture and values — merge profile + JD + careers
        result["culture_and_values"] = profile.get("culture_and_values", {})
        result["culture_and_values"].setdefault("core_values", [])
        if jd.get("culture_signals"):
            result["culture_and_values"]["jd_culture_signals"] = jd["culture_signals"]
        if jd.get("red_flags"):
            result["culture_and_values"]["red_flags"] = jd["red_flags"]
        if careers.get("benefits"):
            result["culture_and_values"]["employee_benefits"] = careers["benefits"]
        if careers.get("work_model"):
            result["culture_and_values"]["work_style"] = careers["work_model"]
        if jd.get("work_model") and jd["work_model"] != "unknown":
            result["culture_and_values"]["work_style"] = jd["work_model"]
        if careers.get("interview_hints"):
            result["culture_and_values"]["interview_hints"] = careers["interview_hints"]

        # Tech and engineering — merge profile + JD + GitHub
        result["tech_and_engineering"] = profile.get("tech_and_engineering", {})
        if jd.get("tech_stack"):
            result["tech_and_engineering"]["jd_tech_stack"] = jd["tech_stack"]
        if jd.get("all_technologies"):
            result["tech_and_engineering"]["tech_stack"] = list(set(
                result["tech_and_engineering"].get("tech_stack", []) + jd["all_technologies"]
            ))
        if github.get("org_name"):
            result["tech_and_engineering"]["github_stats"] = {
                "org_name": github.get("org_name", ""),
                "public_repos": github.get("repo_count", 0),
                "top_languages": list(github.get("languages", {}).keys())[:10],
                "notable_repos": [r.get("name", "") for r in github.get("notable_repos", [])[:5]],
                "activity_level": github.get("activity_level", "Unknown"),
                "total_stars": github.get("total_stars", 0),
                "culture_signals": github.get("culture_signals", []),
                "topics": github.get("topics", [])[:15],
            }

        # Products and services
        result["products_and_services"] = profile.get("products_and_services", {})

        # Market position — merge profile + market intel
        result["market_position"] = profile.get("market_position", {})
        if market.get("competitors") and isinstance(market["competitors"], dict):
            result["market_position"]["market_research"] = {
                k: v for k, v in market.items()
                if k not in ("error",) and isinstance(v, dict)
            }

        # Recent developments
        result["recent_developments"] = profile.get("recent_developments", {})
        if market.get("news") and isinstance(market["news"], dict):
            result["recent_developments"]["news_data"] = market["news"]

        # Hiring intelligence — merge profile + JD + careers
        result["hiring_intelligence"] = profile.get("hiring_intelligence", {})
        if jd.get("must_have_skills"):
            result["hiring_intelligence"]["must_have_skills"] = jd["must_have_skills"]
        if jd.get("nice_to_have_skills"):
            result["hiring_intelligence"]["nice_to_have_skills"] = jd["nice_to_have_skills"]
        if jd.get("seniority"):
            result["hiring_intelligence"]["seniority_signals"] = jd["seniority"]
        if jd.get("years_required"):
            result["hiring_intelligence"]["years_required"] = jd["years_required"]
        if jd.get("salary_range"):
            result["hiring_intelligence"]["salary_range"] = jd["salary_range"]
        if careers.get("estimated_open_roles"):
            result["hiring_intelligence"]["estimated_open_roles"] = careers["estimated_open_roles"]
        if careers.get("ats_platform"):
            result["hiring_intelligence"]["ats_platform"] = careers["ats_platform"]
        if careers.get("teams_hiring"):
            result["hiring_intelligence"]["teams_hiring"] = careers["teams_hiring"]
        if market.get("cross_ref") and isinstance(market["cross_ref"], dict):
            if market["cross_ref"].get("hiring_volume"):
                result["hiring_intelligence"]["hiring_volume"] = market["cross_ref"]["hiring_volume"]

        # Application strategy — from the dedicated strategy agent
        result["application_strategy"] = strategy if strategy else {}
        result["application_strategy"].setdefault("keywords_to_use", [])
        result["application_strategy"].setdefault("values_to_emphasize", [])
        result["application_strategy"].setdefault("things_to_mention", [])
        result["application_strategy"].setdefault("things_to_avoid", [])
        result["application_strategy"].setdefault("cover_letter_hooks", [])
        result["application_strategy"].setdefault("interview_prep_topics", [])
        result["application_strategy"].setdefault("questions_to_ask", [])

        # Confidence — based on data completeness
        has_website = "website_intel" in data_sources
        has_github = "github_intel" in data_sources
        has_careers = "careers_intel" in data_sources
        has_jd = "jd_intel" in data_sources
        has_market = "market_position" in data_sources
        source_count = sum([has_website, has_github, has_careers, has_jd, has_market])

        if source_count >= 4:
            confidence = "high"
        elif source_count >= 3:
            confidence = "medium"
        elif source_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        result["confidence"] = confidence
        result["data_completeness"] = {
            "website_data": has_website,
            "jd_analysis": has_jd,
            "github_data": has_github,
            "careers_page": has_careers,
            "market_data": has_market,
            "company_profile_synthesized": bool(profile),
            "strategy_generated": bool(strategy),
        }

        # Human-readable source names
        source_names = []
        if has_website:
            source_names.append("Company website")
        if has_github:
            source_names.append("GitHub organization")
        if has_careers:
            source_names.append("Careers page")
        if has_jd:
            source_names.append("Job description analysis")
        if has_market:
            source_names.append("Market intelligence")
        if profile:
            source_names.append("AI company profile synthesis")
        if strategy:
            source_names.append("AI application strategy")
        result["data_sources"] = source_names or ["Job description inference only"]

        # Metadata for debugging
        result["_intel_meta"] = {
            "agent_latencies_ms": agent_latencies,
            "total_time_s": round(total_time_s, 2),
            "evidence_count": len(all_evidence),
            "phase1_agents": ["website_intel", "github_intel", "careers_intel", "jd_intel", "market_position"],
            "phase2_agents": ["company_profile", "application_strategy"],
            "version": "2.0",
        }

        # Tier 5 observability passthrough — the coordinator already populated
        # these into raw_intel; we surface them at top level so downstream
        # telemetry / UI doesn't need to dig. All are safe/empty when absent.
        if raw_intel.get("trace") is not None:
            result["trace"] = raw_intel["trace"]
        if raw_intel.get("provider_health") is not None:
            result["provider_health"] = raw_intel["provider_health"]
        if raw_intel.get("profile_schema_audit") is not None:
            result["profile_schema_audit"] = raw_intel["profile_schema_audit"]
        # Always surface the curated evidence list and raw_intel for debugging.
        result["evidence_items"] = all_evidence
        result["raw_intel"] = raw_intel

        return result

    async def _emit(self, callback, message, status, source, url=None, metadata=None):
        if not callback:
            return
        payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
        if url:
            payload["url"] = url
        if metadata:
            payload["metadata"] = metadata
        try:
            maybe = callback(payload)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception:
            pass
