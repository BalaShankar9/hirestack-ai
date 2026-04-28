"""
HireStack AI - Database Module
Supabase integration for data storage (PostgreSQL via PostgREST)
"""
from typing import Optional, Dict, Any, List
import asyncio
import base64
import logging
import os
import random

from supabase import create_client, Client
import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger("hirestack.supabase")


# ── Supabase client singleton ────────────────────────────────────────────────

_supabase_client: Optional[Client] = None


def init_supabase() -> Client:
    """Initialise the Supabase client (service-role, bypasses RLS)."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    _supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_client


def get_supabase() -> Client:
    """Return the Supabase client, initialising if needed."""
    if _supabase_client is None:
        init_supabase()
    return _supabase_client


def close_supabase() -> None:
    """Release the Supabase client singleton (call during shutdown)."""
    global _supabase_client
    if _supabase_client is None:
        return
    try:
        # Close the underlying httpx transport if available
        if hasattr(_supabase_client, "postgrest") and hasattr(_supabase_client.postgrest, "_session"):
            session = _supabase_client.postgrest._session
            if hasattr(session, "aclose") and callable(session.aclose):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(session.aclose())
                except RuntimeError:
                    pass  # No running loop — transport will be GC'd
    except (AttributeError, TypeError) as exc:
        logger.debug("close_supabase minor error: %s", str(exc)[:100])
    _supabase_client = None
    logger.info("Supabase client released")


# ── JWT token verification ───────────────────────────────────────────────────

def _decode_jwt_with_secret(id_token: str, secret) -> Optional[Dict[str, Any]]:
    """Attempt to decode a JWT with the given secret (str or bytes). Returns claims or None."""
    try:
        decoded = jwt.decode(
            id_token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        meta = decoded.get("user_metadata") or {}
        return {
            "sub": str(decoded.get("sub") or ""),
            "email": decoded.get("email"),
            "user_metadata": meta if isinstance(meta, dict) else {},
            "aud": decoded.get("aud"),
            "role": decoded.get("role"),
        }
    except jwt.ExpiredSignatureError:
        raise  # Re-raise so caller can handle expiration specifically
    except jwt.InvalidTokenError:
        return None  # Signature mismatch — try next secret format


def verify_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase access token.

    Prefer local HS256 verification when SUPABASE_JWT_SECRET is configured.
    Tries the raw secret string first, then the base64-decoded bytes (hosted
    Supabase instances may use either format).
    Falls back to the Auth admin API for non-HS256 tokens (e.g. local CLI ES256)
    or when the secret is missing.
    """
    jwt_secret = (settings.supabase_jwt_secret or "").strip()
    if jwt_secret:
        try:
            header = jwt.get_unverified_header(id_token)
            alg = str(header.get("alg") or "").upper()
        except Exception:
            alg = ""

        if alg == "HS256":
            # Try 1: raw secret string (how most Supabase instances work)
            try:
                result = _decode_jwt_with_secret(id_token, jwt_secret)
                if result is not None:
                    return result
            except jwt.ExpiredSignatureError:
                return None

            # Try 2: base64-decoded bytes (some hosted Supabase instances)
            try:
                secret_bytes = base64.b64decode(jwt_secret)
                result = _decode_jwt_with_secret(id_token, secret_bytes)
                if result is not None:
                    return result
            except jwt.ExpiredSignatureError:
                return None
            except Exception as e:
                logger.warning("token_verification_b64_failed", extra={"error": str(e)})

            logger.warning("token_verification_failed_local_all", extra={"note": "both raw and b64 secrets failed, falling back to remote"})

    try:
        client = get_supabase()
        response = client.auth.get_user(id_token)
        if response and response.user:
            user = response.user
            meta = user.user_metadata or {}
            return {
                "sub": str(user.id),
                "email": user.email,
                "user_metadata": meta,
                "aud": "authenticated",
                "role": "authenticated",
            }
        return None
    except Exception as e:
        # Do not treat transient network issues as "invalid token" — callers should
        # use verify_token_async() to get retries + proper 503s.
        logger.warning("token_verification_failed", extra={"error": str(e)})
        return None


def get_user_from_token(decoded_token: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user info from a decoded Supabase JWT."""
    meta = decoded_token.get("user_metadata", {})
    return {
        "uid": decoded_token.get("sub"),
        "email": decoded_token.get("email"),
        "display_name": meta.get("full_name"),
        "photo_url": meta.get("avatar_url"),
    }


# ── Table names ──────────────────────────────────────────────────────────────

TABLES = {
    "users": "users",
    "profiles": "profiles",
    "jobs": "job_descriptions",
    "benchmarks": "benchmarks",
    "gap_reports": "gap_reports",
    "roadmaps": "roadmaps",
    "projects": "projects",
    "documents": "documents",
    "exports": "exports",
    "analytics": "analytics",
    "applications": "applications",
    "evidence": "evidence",
    "tasks": "tasks",
    "events": "events",
    "learning_plans": "learning_plans",
    "doc_versions": "doc_versions",
    "generation_jobs": "generation_jobs",
    "generation_job_events": "generation_job_events",
    "evidence_ledger_items": "evidence_ledger_items",
    "evidence_mappings": "evidence_mappings",
    "claim_citations": "claim_citations",
    "ats_scans": "ats_scans",
    "career_snapshots": "career_snapshots",
    "interview_sessions": "interview_sessions",
    "job_alerts": "job_alerts",
    "job_matches": "job_matches",
    "learning_challenges": "learning_challenges",
    "learning_streaks": "learning_streaks",
    "doc_variants": "doc_variants",
    "salary_analyses": "salary_analyses",
    # Enterprise tables
    "organizations": "organizations",
    "org_members": "org_members",
    "candidates": "candidates",
    "subscriptions": "subscriptions",
    "usage_records": "usage_records",
    "audit_logs": "audit_logs",
    "org_invitations": "org_invitations",
    "webhooks": "webhooks",
    # Review & collaboration
    "review_sessions": "review_sessions",
    "review_comments": "review_comments",
    # Feedback & A/B testing
    "ab_test_results": "ab_test_results",
    # Document catalog (platform-wide)
    "document_type_catalog": "document_type_catalog",
    "document_observations": "document_observations",
    # Document library (user documents across all categories)
    "document_library": "document_library",
    # Outcome tracking (closed-loop quality learning)
    "outcome_signals": "outcome_signals",
    # Pipeline telemetry
    "pipeline_telemetry": "pipeline_telemetry",
    # Agent traces
    "agent_traces": "agent_traces",
    # Pipeline plans (adaptive planner)
    "pipeline_plans": "pipeline_plans",
    # Evidence graph (canonical cross-job nodes)
    "user_evidence_nodes": "user_evidence_nodes",
    "user_evidence_aliases": "user_evidence_aliases",
    "evidence_contradictions": "evidence_contradictions",
    # Autonomous career monitoring
    "career_alerts": "career_alerts",
    # Document evolution tracking
    "document_evolution": "document_evolution",
    # Model quality observations (cost optimizer persistence)
    "quality_observations": "quality_observations",
    # Knowledge library & global skills
    "knowledge_resources": "knowledge_resources",
    "user_knowledge_progress": "user_knowledge_progress",
    "user_skills": "user_skills",
    "user_skill_gaps": "user_skill_gaps",
    "user_learning_goals": "user_learning_goals",
    "resource_recommendations": "resource_recommendations",
    # v4 orchestration foundation (agent_rebuild-tier1-tier2-2026-04-20)
    "agent_artifacts": "agent_artifacts",
    # Stripe webhook idempotency ledger (prod-readiness 2026-04-20)
    "processed_webhook_events": "processed_webhook_events",
}


# ── SupabaseDB helper class ─────────────────────────────────────────────────

class SupabaseDB:
    """
    Async-friendly helper for Supabase/PostgREST operations.

    Wraps the synchronous supabase-py client in ``run_in_executor``
    to avoid blocking the asyncio event loop.  The interface matches
    the previous FirestoreDB class so that existing services work
    without modification.
    """

    def __init__(self):
        self.client: Client = get_supabase()

    @staticmethod
    def _is_transient_error(exc: BaseException) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
            return True
        msg = str(exc).lower()
        return any(token in msg for token in (
            "timed out",
            "timeout",
            "connection reset",
            "server disconnected",
            "temporarily unavailable",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "502",
            "503",
            "504",
        ))

    async def _run(self, func, *args):
        """Execute the (sync) supabase-py call on the default executor.

        Historically wrapped in an asyncio.Lock to serialize all DB calls,
        but the underlying postgrest/httpx client is already thread-safe at
        the connection-pool level, and the SupabaseDB instance is a module
        singleton — so the lock was forcing global serialization of every
        DB call in the process (P-2 in S1 audit). Lock removed; parallel
        DB calls now genuinely run in parallel up to the executor's
        thread-pool size.

        Wrapped in the ``"supabase"`` circuit breaker — only consecutive
        transient errors trip it, so business-logic exceptions (validation,
        RLS denials, etc.) do not poison the breaker.
        """
        loop = asyncio.get_running_loop()
        # Retry tuning lives in Settings (config.py); these are read fresh
        # per call so tests / SIGHUP-style reloads can override at runtime
        # without rebinding the SupabaseDB instance.
        from app.core.config import settings as _settings
        from app.core.circuit_breaker import (
            CircuitBreakerOpen,
            get_breaker_sync,
        )
        attempts = max(1, int(_settings.supabase_http_retries))
        base_delay_s = max(0.05, float(_settings.supabase_http_retry_base_s))
        max_delay_s = max(base_delay_s, float(_settings.supabase_http_retry_max_s))

        breaker = get_breaker_sync("supabase", failure_threshold=10, recovery_timeout=30.0)
        # Gate: short-circuit immediately if the breaker is open.
        try:
            await breaker._before_call()
        except CircuitBreakerOpen:
            raise

        last_exc: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                result = await loop.run_in_executor(None, func, *args)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if SupabaseDB._is_transient_error(exc):
                    await breaker.record_failure()
                # Non-transient errors do NOT trip the breaker (they reflect
                # caller bugs / RLS denials, not Supabase health).
                if attempt >= attempts or not SupabaseDB._is_transient_error(exc):
                    raise
                # Exponential backoff + small jitter.
                delay_s = min(max_delay_s, base_delay_s * (2 ** (attempt - 1))) + random.uniform(0.0, 0.2)
                await asyncio.sleep(delay_s)
                continue
            else:
                await breaker.record_success()
                return result

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Supabase operation failed unexpectedly.")

    # ── Generic CRUD ─────────────────────────────────────────────────────

    @staticmethod
    def _is_table_missing_error(exc: BaseException) -> bool:
        msg = str(exc)
        lower = msg.lower()
        return (
            ("relation" in lower and "does not exist" in lower)
            or "42P01" in msg
            or "PGRST205" in msg
            or "Could not find the table" in msg
            or "schema cache" in lower
        )

    async def create(self, table: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Insert a row. Returns the generated (or supplied) id."""
        safe = {k: v for k, v in data.items() if k not in ("created_at", "updated_at")}
        if doc_id:
            safe["id"] = doc_id

        def _ins():
            result = self.client.table(table).insert(safe).execute()
            return str(result.data[0]["id"]) if result.data else None

        try:
            return await self._run(_ins)
        except Exception as e:
            if self._is_table_missing_error(e):
                logger.error("table_missing_on_create: table=%s error=%s", table, str(e)[:200])
                raise RuntimeError(f"Database table '{table}' does not exist. Run migrations first.") from e
            raise

    async def get(self, table: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single row by id."""
        def _get():
            result = self.client.table(table).select("*").eq("id", str(doc_id)).limit(1).execute()
            data = result.data or []
            if isinstance(data, list):
                return data[0] if data else None
            return data

        try:
            return await self._run(_get)
        except Exception as e:
            if self._is_table_missing_error(e):
                logger.error("table_missing_on_get: table=%s error=%s", table, str(e)[:200])
                raise RuntimeError(f"Database table '{table}' does not exist. Run migrations first.") from e
            raise

    async def update(self, table: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update a row by id. updated_at is handled by DB trigger."""
        safe = {k: v for k, v in data.items() if k not in ("created_at", "updated_at")}

        def _upd():
            self.client.table(table).update(safe).eq("id", str(doc_id)).execute()

        await self._run(_upd)
        return True

    async def delete(self, table: str, doc_id: str) -> bool:
        """Delete a row by id."""
        def _del():
            self.client.table(table).delete().eq("id", str(doc_id)).execute()

        await self._run(_del)
        return True

    async def delete_where(self, table: str, filters: Optional[List[tuple]] = None) -> bool:
        """Delete rows matching the provided filters."""
        def _del_where():
            q = self.client.table(table).delete()
            if filters:
                for field, op, value in filters:
                    if op == "==":
                        q = q.eq(field, value)
                    elif op == "!=":
                        q = q.neq(field, value)
                    elif op == ">":
                        q = q.gt(field, value)
                    elif op == ">=":
                        q = q.gte(field, value)
                    elif op == "<":
                        q = q.lt(field, value)
                    elif op == "<=":
                        q = q.lte(field, value)
                    elif op == "in":
                        q = q.in_(field, value)
                    else:
                        q = q.eq(field, value)
            q.execute()

        try:
            await self._run(_del_where)
            return True
        except Exception as e:
            if self._is_table_missing_error(e):
                logger.error("table_missing_on_delete_where: table=%s error=%s", table, str(e)[:200])
                raise RuntimeError(f"Database table '{table}' does not exist. Run migrations first.") from e
            raise

    async def query(
        self,
        table: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        order_direction: str = "DESCENDING",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query rows with optional filters, ordering, limit, and offset."""
        def _q():
            q = self.client.table(table).select("*")
            if filters:
                for field, op, value in filters:
                    if op == "==":
                        q = q.eq(field, value)
                    elif op == "!=":
                        q = q.neq(field, value)
                    elif op == ">":
                        q = q.gt(field, value)
                    elif op == ">=":
                        q = q.gte(field, value)
                    elif op == "<":
                        q = q.lt(field, value)
                    elif op == "<=":
                        q = q.lte(field, value)
                    elif op == "in":
                        q = q.in_(field, value)
                    else:
                        q = q.eq(field, value)
            if order_by:
                desc = order_direction == "DESCENDING"
                q = q.order(order_by, desc=desc)
            if limit:
                q = q.limit(limit)
            if offset:
                q = q.offset(offset)
            result = q.execute()
            return result.data or []

        try:
            return await self._run(_q)
        except Exception as e:
            if self._is_table_missing_error(e):
                logger.error("table_missing_on_query: table=%s error=%s", table, str(e)[:200])
                raise RuntimeError(f"Database table '{table}' does not exist. Run migrations first.") from e
            raise

    # ── User helpers ─────────────────────────────────────────────────────

    async def get_user_by_auth_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get user by Supabase Auth UID (same as users.id)."""
        return await self.get(TABLES["users"], uid)

    async def get_or_create_user(
        self,
        uid: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get existing user or create one (usually auto-created by DB trigger)."""
        user = await self.get_user_by_auth_uid(uid)
        if not user:
            user_data = {
                "id": uid,
                "email": email,
                "full_name": full_name,
                "avatar_url": avatar_url,
                "is_active": True,
                "is_premium": False,
            }
            await self.create(TABLES["users"], user_data, doc_id=uid)
            user = await self.get(TABLES["users"], uid)
        return user


class AuthServiceUnavailable(RuntimeError):
    """Raised when Supabase Auth verification is temporarily unavailable."""


# ── Token verification cache ─────────────────────────────────────────────────
# Caches successful token verifications to avoid redundant remote calls.
# Keyed by a truncated SHA-256 hash of the token (not the token itself).
# Expires entries when the JWT's `exp` claim has passed.

import hashlib  # noqa: E402
import time as _time  # noqa: E402
from collections import OrderedDict  # noqa: E402

_TOKEN_CACHE_MAX_SIZE = 256
_NEGATIVE_CACHE_MAX_SIZE = 512
_NEGATIVE_CACHE_TTL_S = 60.0  # short — gives revoked/refreshed tokens a chance


class _TokenCache:
    """LRU cache for verified JWT claims, keyed by token hash.

    Carries a separate, smaller-TTL *negative* cache so a flood of garbage
    bearer tokens cannot pin the event loop on /auth/v1/user calls or
    repeated PyJWT decode work (S1-F5: closes S-3 DoS amplifier).
    """

    def __init__(
        self,
        max_size: int = _TOKEN_CACHE_MAX_SIZE,
        *,
        negative_max_size: int = _NEGATIVE_CACHE_MAX_SIZE,
        negative_ttl_s: float = _NEGATIVE_CACHE_TTL_S,
    ):
        self._cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._max_size = max_size
        self._negative: OrderedDict[str, float] = OrderedDict()
        self._negative_max_size = negative_max_size
        self._negative_ttl_s = negative_ttl_s

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]

    def get(self, token: str) -> Optional[Dict[str, Any]]:
        key = self._key(token)
        entry = self._cache.get(key)
        if entry is None:
            return None
        claims, expires_at = entry
        if _time.time() >= expires_at:
            self._cache.pop(key, None)
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return claims

    def put(self, token: str, claims: Dict[str, Any]) -> None:
        key = self._key(token)
        # Use JWT exp claim; fall back to 5 minutes
        exp = claims.get("exp") or (_time.time() + 300)
        if isinstance(exp, (int, float)):
            expires_at = float(exp)
        else:
            expires_at = _time.time() + 300
        self._cache[key] = (claims, expires_at)
        self._cache.move_to_end(key)
        # Evict oldest if over limit
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        # A token cannot be both valid and known-bad simultaneously.
        self._negative.pop(key, None)

    def is_known_bad(self, token: str) -> bool:
        """Return True if *token* failed verification recently (< TTL)."""
        key = self._key(token)
        expires_at = self._negative.get(key)
        if expires_at is None:
            return False
        if _time.time() >= expires_at:
            self._negative.pop(key, None)
            return False
        self._negative.move_to_end(key)
        return True

    def mark_bad(self, token: str) -> None:
        """Remember that *token* failed verification — short TTL."""
        key = self._key(token)
        self._negative[key] = _time.time() + self._negative_ttl_s
        self._negative.move_to_end(key)
        while len(self._negative) > self._negative_max_size:
            self._negative.popitem(last=False)

    def invalidate(self, token: str) -> None:
        key = self._key(token)
        self._cache.pop(key, None)
        self._negative.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
        self._negative.clear()


_token_cache = _TokenCache()


async def verify_token_async(id_token: str, db: Optional[SupabaseDB] = None) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase access token.
    0. Check LRU cache for previously verified token.
    1. Fast-path: local HS256 decode (no I/O — uses SUPABASE_JWT_SECRET).
    2. Async remote fallback: calls Supabase /auth/v1/user in a thread executor
       (never blocks the event loop).
    """
    # ── 0. Cache hit ──────────────────────────────────────────────────
    cached = _token_cache.get(id_token)
    if cached is not None:
        return cached

    # ── 0b. Negative cache: short-circuit recently-failed tokens. ─────
    # Closes S-3: a flood of garbage bearer tokens previously cost a
    # PyJWT decode + (sometimes) a remote /auth/v1/user round-trip on
    # every request. 60s TTL is short enough that real tokens minted
    # right after a failure are still given a chance to verify.
    if _token_cache.is_known_bad(id_token):
        return None

    # ── 1. Local JWT decode (no network I/O) ──────────────────────────
    jwt_secret = (settings.supabase_jwt_secret or "").strip()
    if jwt_secret:
        try:
            header = jwt.get_unverified_header(id_token)
            alg = str(header.get("alg") or "").upper()
        except Exception:
            alg = ""

        if alg == "HS256":
            # Try 1: raw secret string
            try:
                result = _decode_jwt_with_secret(id_token, jwt_secret)
                if result is not None:
                    _token_cache.put(id_token, result)
                    return result
            except jwt.ExpiredSignatureError:
                _token_cache.mark_bad(id_token)
                return None

            # Try 2: base64-decoded bytes
            try:
                secret_bytes = base64.b64decode(jwt_secret)
                result = _decode_jwt_with_secret(id_token, secret_bytes)
                if result is not None:
                    _token_cache.put(id_token, result)
                    return result
            except jwt.ExpiredSignatureError:
                _token_cache.mark_bad(id_token)
                return None
            except Exception as e:
                logger.warning("token_verification_b64_failed", extra={"error": str(e)})

    # ── 2. Async remote verification (runs in thread, never blocks loop) ──
    _db = db or get_db()

    def _get_user():
        return _db.client.auth.get_user(id_token)

    try:
        response = await _db._run(_get_user)
    except Exception as exc:
        # Treat transient network/timeouts as service-unavailable so the API can
        # return a retryable 503 instead of a confusing 401. Do NOT add to the
        # negative cache — the token may be valid; the dependency was sick.
        if SupabaseDB._is_transient_error(exc):
            raise AuthServiceUnavailable("Supabase auth verification timed out") from exc
        logger.warning("token_verification_failed_async", extra={"error": str(exc)})
        _token_cache.mark_bad(id_token)
        return None

    if response and getattr(response, "user", None):
        user = response.user
        meta = user.user_metadata or {}
        claims = {
            "sub": str(user.id),
            "email": user.email,
            "user_metadata": meta,
            "aud": "authenticated",
            "role": "authenticated",
        }
        _token_cache.put(id_token, claims)
        return claims
    # Remote returned no user → token is bad. Cache the rejection.
    _token_cache.mark_bad(id_token)
    return None


# ── Backward-compatible aliases ──────────────────────────────────────────────
# Existing services import FirestoreDB / get_firestore_db / COLLECTIONS /
# verify_firebase_token.  These aliases let them work without modification.

COLLECTIONS = TABLES
FirestoreDB = SupabaseDB
verify_firebase_token = verify_token


_db_instance: Optional[SupabaseDB] = None


def get_db() -> SupabaseDB:
    """Get SupabaseDB singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = SupabaseDB()
    return _db_instance


def get_firestore_db() -> SupabaseDB:
    """Backward-compat alias for get_db()."""
    return get_db()


def get_firebase_user(uid: str) -> Optional[Dict[str, Any]]:
    """Backward-compat stub — not used with Supabase."""
    return None


# Keep init_firebase as alias so main.py lifespan doesn't break during migration
def init_firebase():
    """Alias — initialises Supabase instead."""
    init_supabase()


# ── Redis response cache ─────────────────────────────────────────────────────
# Cache layer extracted to app.core.cache (S1-F10).
# Re-exported here for back-compat with existing importers.
from app.core.cache import (  # noqa: E402,F401
    cache_get,
    cache_invalidate,
    cache_invalidate_prefix,
    cache_set,
    get_redis,
)
