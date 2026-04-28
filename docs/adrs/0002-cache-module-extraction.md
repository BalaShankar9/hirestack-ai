# ADR-0002: Extract cache layer into `app.core.cache`

Status: Accepted — 2026-04-21 (S1-F10)
Owners: Platform Core squad

## Context

`app/core/database.py` had grown to 867 LOC by mixing four concerns:

1. Supabase client lifecycle and CRUD wrapper (`SupabaseDB`).
2. JWT verification helpers (`verify_token`, `verify_token_async`).
3. Negative-auth-cache (`_TokenCache`).
4. **Redis + in-memory LRU cache helpers** (`get_redis`, `cache_get`,
   `cache_set`, `cache_invalidate`, `cache_invalidate_prefix`).

The cache concern is logically independent of database access — it
is consumed by services, routes, and the AI engine — yet imports
fanned out from `app.core.database` everywhere. This created a
classic god-module: changing cache behaviour required reading 800+
lines of unrelated code.

## Decision

Move the cache surface to a new module **`app.core.cache`** with
the public exports:

```
get_redis
cache_get
cache_set
cache_invalidate
cache_invalidate_prefix
```

Implementation details:

- Lazy Redis init (single client per process) using `settings.redis_url`.
- 512-entry in-memory `OrderedDict` LRU as **fallback** when Redis
  is unreachable. Operations never raise — cache is best-effort.
- Default TTL pulled from `settings.cache_ttl_seconds`.
- Logger name `hirestack.cache`.

`app.core.database` retains a back-compat re-export
(`from app.core.cache import …`) so the 14 existing importers do
not break. New code MUST import from `app.core.cache` directly.

## Consequences

- `database.py` shrinks to 756 LOC (still large; further extraction
  of JWT helpers and the back-compat Firestore aliases is tracked
  in the next refactor PR).
- Cache changes (TTL tuning, swapping the eviction policy, adding
  Sentinel support) now happen in a 154-LOC focused module with
  its own test (`test_cache_module.py`).
- The in-memory fallback is the explicit reason `/healthz/ready`
  treats Redis as optional (see ADR-0003).

## Alternatives considered

- **Leave it in `database.py`** — rejected. Future cache changes
  would keep accreting code in a module that also handles auth,
  multiplying review cost.
- **Split everything (Auth, JWT, DB, cache) in one PR** —
  rejected. Touches dozens of importers across the repo and
  blows past the squad's 500-LOC budget. Done as an incremental
  refactor instead.
