"""Tool registry (PR m5-pr14): lookup, grant, validate, dispatch, audit.

Gated by ``ff_tool_registry``. When OFF the dispatcher refuses every
call (RegistryDisabled), keeping legacy in-memory tool plumbing intact.
"""

from .dispatcher import (
    Dispatcher,
    GrantDenied,
    InvalidInput,
    InvalidOutput,
    RegistryDisabled,
    ToolInvocation,
    ToolNotFound,
    ToolTimeout,
)
from .supabase_store import SupabaseToolStore, supabase_invocation_sink
from .tools import ToolRecord, ToolStore

__all__ = [
    "Dispatcher",
    "GrantDenied",
    "InvalidInput",
    "InvalidOutput",
    "RegistryDisabled",
    "SupabaseToolStore",
    "ToolInvocation",
    "ToolNotFound",
    "ToolStore",
    "ToolRecord",
    "ToolTimeout",
    "supabase_invocation_sink",
]
