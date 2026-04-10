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


# ── JWT token verification ───────────────────────────────────────────────────

def _decode_jwt_with_secret(id_token: str, secret) -> Optional[Dict[str, Any]]:
    """Attempt to decode a JWT with the given secret (str or bytes). Returns claims or None."""
    try:
        decoded = jwt.decode(
            id_token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
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
        self._lock: Optional[asyncio.Lock] = None

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
        loop = asyncio.get_running_loop()
        if self._lock is None:
            # Create lock inside the running loop (py3.9 asyncio primitives can be loop-bound).
            self._lock = asyncio.Lock()
        attempts_raw = os.getenv("SUPABASE_HTTP_RETRIES", "3")
        base_delay_raw = os.getenv("SUPABASE_HTTP_RETRY_BASE_S", "0.25")
        max_delay_raw = os.getenv("SUPABASE_HTTP_RETRY_MAX_S", "2.0")
        try:
            attempts = max(1, int(attempts_raw))
        except Exception:
            attempts = 3
        try:
            base_delay_s = max(0.05, float(base_delay_raw))
        except Exception:
            base_delay_s = 0.25
        try:
            max_delay_s = max(base_delay_s, float(max_delay_raw))
        except Exception:
            max_delay_s = 2.0

        last_exc: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                async with self._lock:
                    return await loop.run_in_executor(None, func, *args)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts or not SupabaseDB._is_transient_error(exc):
                    raise
                # Exponential backoff + small jitter.
                delay_s = min(max_delay_s, base_delay_s * (2 ** (attempt - 1))) + random.uniform(0.0, 0.2)
                await asyncio.sleep(delay_s)

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
                logger.warning("table_missing_on_create: %s", table)
                # Return a fake ID so callers don't crash — data won't persist
                import uuid
                return str(uuid.uuid4())
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
                logger.warning("table_missing_on_get: %s", table)
                return None
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

    async def query(
        self,
        table: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        order_direction: str = "DESCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query rows with optional filters, ordering, and limit."""
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
            result = q.execute()
            return result.data or []

        try:
            return await self._run(_q)
        except Exception as e:
            if self._is_table_missing_error(e):
                logger.warning("table_missing_on_query: %s", table)
                return []
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


async def verify_token_async(id_token: str, db: Optional[SupabaseDB] = None) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase access token.
    1. Fast-path: local HS256 decode (no I/O — uses SUPABASE_JWT_SECRET).
    2. Async remote fallback: calls Supabase /auth/v1/user in a thread executor
       (never blocks the event loop).
    """
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
                    return result
            except jwt.ExpiredSignatureError:
                return None

            # Try 2: base64-decoded bytes
            try:
                secret_bytes = base64.b64decode(jwt_secret)
                result = _decode_jwt_with_secret(id_token, secret_bytes)
                if result is not None:
                    return result
            except jwt.ExpiredSignatureError:
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
        # return a retryable 503 instead of a confusing 401.
        if SupabaseDB._is_transient_error(exc):
            raise AuthServiceUnavailable("Supabase auth verification timed out") from exc
        logger.warning("token_verification_failed_async", extra={"error": str(exc)})
        return None

    if response and getattr(response, "user", None):
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
