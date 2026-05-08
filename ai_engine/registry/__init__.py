"""Tool registry (PR m5-pr14): lookup, grant, validate, dispatch, audit.

Gated by ``ff_tool_registry``. When OFF the dispatcher refuses every
call (RegistryDisabled), keeping legacy in-memory tool plumbing intact.
"""

from .capability import (
    Authorizer,
    CapabilityConfigError,
    CapabilityError,
    CapabilityInvalid,
    CapabilityToken,
    InProcessNonceStore,
    RedisNonceStore,
)
from .dispatcher import (
    CapabilityRequired,
    Dispatcher,
    GrantDenied,
    InvalidInput,
    InvalidOutput,
    RegistryDisabled,
    ToolInvocation,
    ToolNotFound,
    ToolTimeout,
)
from .resolvers import RESOLVERS, UnknownCodeRef, resolve
from .sandboxes import (
    L0InProcessSandbox,
    L1HttpxAllowlistSandbox,
    L2GrpcSidecarSandbox,
    Sandbox,
    SandboxNotImplemented,
    UnknownSandboxTier,
    default_sandboxes,
    is_routing_enabled,
    select_sandbox,
)
from .supabase_store import SupabaseToolStore, supabase_invocation_sink
from .tools import ToolRecord, ToolStore

__all__ = [
    "Authorizer",
    "CapabilityConfigError",
    "CapabilityError",
    "CapabilityInvalid",
    "CapabilityRequired",
    "CapabilityToken",
    "Dispatcher",
    "GrantDenied",
    "InProcessNonceStore",
    "InvalidInput",
    "InvalidOutput",
    "L0InProcessSandbox",
    "L1HttpxAllowlistSandbox",
    "L2GrpcSidecarSandbox",
    "RESOLVERS",
    "RedisNonceStore",
    "RegistryDisabled",
    "Sandbox",
    "SandboxNotImplemented",
    "SupabaseToolStore",
    "ToolInvocation",
    "ToolNotFound",
    "ToolRecord",
    "ToolStore",
    "ToolTimeout",
    "UnknownCodeRef",
    "UnknownSandboxTier",
    "default_sandboxes",
    "is_routing_enabled",
    "resolve",
    "select_sandbox",
    "supabase_invocation_sink",
]
