"""Canonical ``code_ref`` resolver allowlist (ADR-0033, PR m7-pr29).

Today's seeded tools (``search_user_history``, ``extract_claims``)
have ``code_ref`` strings pointing to functions that don't exist in
production yet — the registry has zero production callers, only tests.
``RESOLVERS`` therefore starts as the empty dict, and ``resolve()``
raises ``UnknownCodeRef`` for everything.

As real resolvers land (m7-pr29b+, when the orchestrator first calls
``Dispatcher.invoke`` for real), each new entry MUST be added here in
the same PR — that is the AP-4 governance hook. The empty-but-strict
map is the load-bearing part: it makes "I'll wire the resolver later"
impossible.

Test fixtures bypass this by passing ``resolver=lambda _ref: fn``
to the Dispatcher constructor; the canonical ``resolve`` is the
production default.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Final


class UnknownCodeRef(LookupError):
    """A tool's ``code_ref`` is not in the canonical RESOLVERS map."""


# Empty by design — see module docstring.
# To add a resolver: import the callable above and add an entry here.
RESOLVERS: Final[dict[str, Callable[..., Awaitable[Any]]]] = {}


def resolve(code_ref: str) -> Callable[..., Awaitable[Any]]:
    """Return the callable for ``code_ref`` or raise ``UnknownCodeRef``."""
    try:
        return RESOLVERS[code_ref]
    except KeyError as exc:
        raise UnknownCodeRef(code_ref) from exc


__all__ = ["RESOLVERS", "UnknownCodeRef", "resolve"]
