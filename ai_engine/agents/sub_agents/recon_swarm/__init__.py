"""S18 — Recon Swarm v2: Deep Intelligence Engine.

5-layer OSINT architecture with pluggable source providers, structured
intel fusion, application weaponization, TTL cache, and budget-aware
parallel coordination.

Layers:
  1. Source Discovery       — N parallel providers (Crunchbase, LinkedIn,
                              BuiltWith, GitHub, GoogleNews, ProductHunt,
                              SEC, Patent, Glassdoor, Twitter)
  2. Deep Content Extraction — Website fetch + LLM-chunked extraction
  3. Structured Synthesis    — IntelFusion merges N raw signals → 50+
                              fields with per-field confidence
  4. Application Weaponization — ApplicationMapper turns intel into
                                resume hooks, cover letter hooks,
                                interview Q kit, talking points
  5. Delivery                — ReconSwarmReport (frontend dashboard JSON)

All providers default to deterministic offline stubs. Real-API impls
slot in when env keys are configured (HEYGEN-style pattern from S17-P4).
"""
from __future__ import annotations

from .application_mapper import ApplicationMapper
from .cache import IntelCache, get_default_cache
from .coordinator_v2 import ReconSwarmCoordinator, run_recon_swarm
from .intel_fusion import IntelFusion
from .integration import build_recon_swarm_tools, detect_recon_swarm_intent
from .providers import (
    SourceProvider,
    StubBuiltWithProvider,
    StubCrunchbaseProvider,
    StubGitHubProvider,
    StubGlassdoorProvider,
    StubGoogleNewsProvider,
    StubLinkedInProvider,
    StubPatentProvider,
    StubProductHuntProvider,
    StubSECProvider,
    StubTwitterProvider,
    default_layer1_providers,
    default_layer2_providers,
)
from .schemas import (
    ApplicationKit,
    CompanyIntelV2,
    IntelField,
    ProviderResult,
    ReconSwarmReport,
    ReconSwarmRequest,
)

__all__ = [
    "ApplicationKit",
    "ApplicationMapper",
    "CompanyIntelV2",
    "IntelCache",
    "IntelField",
    "IntelFusion",
    "ProviderResult",
    "ReconSwarmCoordinator",
    "ReconSwarmReport",
    "ReconSwarmRequest",
    "SourceProvider",
    "StubBuiltWithProvider",
    "StubCrunchbaseProvider",
    "StubGitHubProvider",
    "StubGlassdoorProvider",
    "StubGoogleNewsProvider",
    "StubLinkedInProvider",
    "StubPatentProvider",
    "StubProductHuntProvider",
    "StubSECProvider",
    "StubTwitterProvider",
    "build_recon_swarm_tools",
    "default_layer1_providers",
    "default_layer2_providers",
    "detect_recon_swarm_intent",
    "get_default_cache",
    "run_recon_swarm",
]
