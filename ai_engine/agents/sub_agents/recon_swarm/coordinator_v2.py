"""S18 — 5-Layer Recon Swarm Coordinator (v2).

Run model:
  Layer 1 — Source Discovery       (asyncio.gather, per-agent timeout 30s)
  Layer 2 — Deep Content Extraction (asyncio.gather, per-agent timeout 60s)
  Layer 3 — Structured Synthesis   (IntelFusion)
  Layer 4 — Application Weaponization (ApplicationMapper)
  Layer 5 — Delivery               (ReconSwarmReport assembly)

Hard guards:
  - Total budget_seconds (default 180s); coordinator hard-stops if exceeded.
  - Per-provider timeout + 1 retry with linear backoff.
  - All provider failures degrade gracefully (returned as failed
    ProviderResult; fusion still runs).
  - Cache-by-input-hash with TTL 86400s by default.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, List, Optional

from ai_engine.agent_events import (
    emit_cache_hit,
    emit_phase,
    emit_tool_call,
    emit_tool_result,
)

from .application_mapper import ApplicationMapper
from .cache import IntelCache, cache_key, get_default_cache
from .intel_fusion import IntelFusion
from .providers import (
    SourceProvider,
    default_layer1_providers,
    default_layer2_providers,
)
from .schemas import (
    ApplicationKit,
    CompanyIntelV2,
    ProviderResult,
    ReconSwarmReport,
    ReconSwarmRequest,
)

logger = logging.getLogger(__name__)

_LAYER1_PROVIDER_TIMEOUT_S = 30.0
_LAYER2_PROVIDER_TIMEOUT_S = 60.0
_DEFAULT_TTL_S = 24 * 3600


class ReconSwarmCoordinator:
    def __init__(
        self,
        *,
        ai_client: Optional[Any] = None,
        layer1: Optional[List[SourceProvider]] = None,
        layer2: Optional[List[SourceProvider]] = None,
        cache: Optional[IntelCache] = None,
        cache_ttl_s: int = _DEFAULT_TTL_S,
    ) -> None:
        self.ai_client = ai_client
        self.layer1 = layer1 if layer1 is not None else default_layer1_providers()
        self.layer2 = layer2 if layer2 is not None else default_layer2_providers()
        self.fusion = IntelFusion(ai_client=ai_client)
        self.mapper = ApplicationMapper()
        self.cache = cache or get_default_cache()
        self.cache_ttl_s = cache_ttl_s

    # ─── public ────────────────────────────────────────────────

    async def run(self, request: ReconSwarmRequest) -> ReconSwarmReport:
        if not request.company.strip():
            raise ValueError("company is required")
        started = time.perf_counter()
        emit_phase(
            "swarm",
            "running",
            agent="recon_swarm",
            stage="discovery",
            message=f"Deploying {len(self.layer1) + len(self.layer2)} intel agents for {request.company}",
            metadata={
                "company": request.company,
                "role_target": request.role_target,
                "providers_l1": len(self.layer1),
                "providers_l2": len(self.layer2),
                "budget_seconds": request.budget_seconds,
            },
        )
        key = cache_key({
            "c": request.company.strip().lower(),
            "r": (request.role_target or "").strip().lower(),
            "w": (request.website or "").strip().lower(),
            "s": sorted({s.lower() for s in request.candidate_skills}),
            "v": sorted({v.lower() for v in request.candidate_values}),
        })

        if request.use_cache:
            cached = await self.cache.get(key)
            if cached:
                cached["cache_hit"] = True
                cached["total_latency_ms"] = int(
                    (time.perf_counter() - started) * 1000
                )
                emit_cache_hit(
                    "recon_swarm",
                    agent="recon_swarm",
                    saved_ms=cached.get("total_latency_ms"),
                    key_preview=key[:24],
                )
                emit_phase(
                    "swarm",
                    "completed",
                    agent="recon_swarm",
                    stage="delivery",
                    message=f"Recon swarm served from cache for {request.company}",
                    metadata={"cache_hit": True, "company": request.company},
                    latency_ms=cached["total_latency_ms"],
                )
                return ReconSwarmReport(**cached)

        budget = float(request.budget_seconds)
        layers_completed: List[int] = []
        ctx = {
            "website": request.website,
            "is_public": False,  # set after layer 1 if SEC ticker found
            "allow_network": False,
        }

        # Layer 1
        l1_started = time.perf_counter()
        emit_phase(
            "layer1",
            "running",
            agent="recon_swarm",
            stage="source_discovery",
            message=f"Fanning out to {len(self.layer1)} Layer-1 sources",
            metadata={"providers": [getattr(p, "name", "?") for p in self.layer1]},
        )
        l1_results = await self._run_layer(
            self.layer1,
            ctx,
            request.company,
            timeout_s=_LAYER1_PROVIDER_TIMEOUT_S,
            deadline=started + budget,
            stage="source_discovery",
        )
        layers_completed.append(1)
        l1_success = sum(1 for r in l1_results if r.success)
        emit_phase(
            "layer1",
            "completed",
            agent="recon_swarm",
            stage="source_discovery",
            message=f"Layer 1 complete: {l1_success}/{len(l1_results)} sources",
            metadata={
                "success_count": l1_success,
                "total": len(l1_results),
            },
            latency_ms=int((time.perf_counter() - l1_started) * 1000),
        )
        # Adapt context for layer 2
        for r in l1_results:
            if r.success and r.raw.get("ticker"):
                ctx["is_public"] = True
                break

        # Layer 2 (only if budget remains)
        l2_results: List[ProviderResult] = []
        if (time.perf_counter() - started) < budget:
            l2_started = time.perf_counter()
            emit_phase(
                "layer2",
                "running",
                agent="recon_swarm",
                stage="deep_extraction",
                message=f"Fanning out to {len(self.layer2)} Layer-2 sources",
                metadata={"providers": [getattr(p, "name", "?") for p in self.layer2]},
            )
            l2_results = await self._run_layer(
                self.layer2,
                ctx,
                request.company,
                timeout_s=_LAYER2_PROVIDER_TIMEOUT_S,
                deadline=started + budget,
                stage="deep_extraction",
            )
            layers_completed.append(2)
            l2_success = sum(1 for r in l2_results if r.success)
            emit_phase(
                "layer2",
                "completed",
                agent="recon_swarm",
                stage="deep_extraction",
                message=f"Layer 2 complete: {l2_success}/{len(l2_results)} sources",
                metadata={
                    "success_count": l2_success,
                    "total": len(l2_results),
                },
                latency_ms=int((time.perf_counter() - l2_started) * 1000),
            )
        else:
            emit_phase(
                "layer2",
                "skipped",
                agent="recon_swarm",
                stage="deep_extraction",
                message="Budget exhausted before Layer 2",
            )
            logger.info("recon_swarm budget exhausted before layer 2")

        all_results = l1_results + l2_results

        # Layer 3 — Fusion
        fusion_started = time.perf_counter()
        emit_phase(
            "fusion",
            "running",
            agent="recon_swarm",
            stage="synthesis",
            message="Fusing evidence into structured intel",
            metadata={"provider_results": len(all_results)},
        )
        intel: CompanyIntelV2 = await self.fusion.fuse(
            request.company, all_results,
        )
        layers_completed.append(3)
        emit_phase(
            "fusion",
            "completed",
            agent="recon_swarm",
            stage="synthesis",
            message=f"Synthesis complete: {intel.field_count} fields populated",
            metadata={
                "field_count": intel.field_count,
                "evidence_count": len(intel.evidence) if hasattr(intel, "evidence") else 0,
            },
            latency_ms=int((time.perf_counter() - fusion_started) * 1000),
        )

        # Layer 4 — Application kit
        mapper_started = time.perf_counter()
        emit_phase(
            "mapper",
            "running",
            agent="recon_swarm",
            stage="weaponization",
            message="Mapping intel into application hooks",
        )
        kit: ApplicationKit = self.mapper.map(
            intel,
            role_target=request.role_target,
            candidate_skills=request.candidate_skills,
            candidate_values=request.candidate_values,
        )
        layers_completed.append(4)
        emit_phase(
            "mapper",
            "completed",
            agent="recon_swarm",
            stage="weaponization",
            message=f"Application kit ready: {len(kit.cover_letter_hooks)} hooks, {len(kit.interview_questions)} interview Qs",
            metadata={
                "cover_letter_hooks": len(kit.cover_letter_hooks),
                "interview_questions": len(kit.interview_questions),
                "talking_points": len(kit.talking_points),
                "differentiation_angles": len(kit.differentiation_angles),
                "red_flags": len(kit.red_flags),
            },
            latency_ms=int((time.perf_counter() - mapper_started) * 1000),
        )

        # Layer 5 — Assemble report
        report = ReconSwarmReport(
            company=request.company,
            intel=intel,
            application_kit=kit,
            provider_results=all_results,
            layers_completed=layers_completed + [5],
            cache_hit=False,
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            budget_seconds=request.budget_seconds,
        )
        # Store in cache
        if request.use_cache:
            await self.cache.set(
                key, report.model_dump(), ttl_s=self.cache_ttl_s,
            )
        emit_phase(
            "swarm",
            "completed",
            agent="recon_swarm",
            stage="delivery",
            message=f"Recon swarm complete for {request.company}",
            metadata={
                "layers_completed": report.layers_completed,
                "field_count": intel.field_count,
                "cache_hit": False,
            },
            latency_ms=report.total_latency_ms,
        )
        return report

    # ─── internals ─────────────────────────────────────────────

    async def _run_layer(
        self,
        providers: List[SourceProvider],
        ctx: dict,
        company: str,
        *,
        timeout_s: float,
        deadline: float,
        stage: Optional[str] = None,
    ) -> List[ProviderResult]:
        if not providers:
            return []
        tasks = [
            self._run_provider(p, company, ctx, timeout_s, deadline, stage=stage)
            for p in providers
        ]
        return await asyncio.gather(*tasks)

    async def _run_provider(
        self,
        provider: SourceProvider,
        company: str,
        ctx: dict,
        timeout_s: float,
        deadline: float,
        *,
        stage: Optional[str] = None,
    ) -> ProviderResult:
        provider_name = getattr(provider, "name", "unknown")
        provider_layer = getattr(provider, "layer", 0)
        emit_tool_call(
            provider_name,
            {"company": company, "layer": provider_layer},
            agent="recon_swarm",
            stage=stage,
        )
        remaining = max(0.5, deadline - time.perf_counter())
        per_call_timeout = min(timeout_s, remaining)
        last_exc: Optional[Exception] = None
        provider_started = time.perf_counter()
        for attempt in (1, 2):
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    provider.fetch(company=company, **ctx),
                    timeout=per_call_timeout,
                )
                emit_tool_result(
                    provider_name,
                    {
                        "layer": provider_layer,
                        "success": result.success,
                        "fields": list(result.raw.keys())[:8] if result.raw else [],
                    },
                    agent="recon_swarm",
                    stage=stage,
                    latency_ms=int((time.perf_counter() - provider_started) * 1000),
                    success=result.success,
                    error=result.error,
                )
                return result
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.info(
                    "recon provider timeout name=%s attempt=%d",
                    provider_name, attempt,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.info(
                    "recon provider error name=%s attempt=%d exc=%s",
                    provider_name, attempt, exc,
                )
            if attempt == 1:
                await asyncio.sleep(0.05)  # tiny linear backoff
        emit_tool_result(
            provider_name,
            {"layer": provider_layer, "success": False},
            agent="recon_swarm",
            stage=stage,
            latency_ms=int((time.perf_counter() - provider_started) * 1000),
            success=False,
            error=str(last_exc)[:200] if last_exc else "unknown",
        )
        return ProviderResult(
            provider=provider_name,
            layer=provider_layer,
            success=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(last_exc)[:200] if last_exc else "unknown",
        )


async def run_recon_swarm(
    request: ReconSwarmRequest,
    *,
    ai_client: Optional[Any] = None,
    coordinator: Optional[ReconSwarmCoordinator] = None,
) -> ReconSwarmReport:
    coord = coordinator or ReconSwarmCoordinator(ai_client=ai_client)
    return await coord.run(request)
