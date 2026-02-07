"""
HireStack AI - Database Module
Supabase integration for data storage (PostgreSQL via PostgREST)
"""
from typing import Optional, Dict, Any, List
import asyncio

from supabase import create_client, Client

from app.core.config import settings


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

def verify_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase access token by calling the Auth admin API.

    Works with both HS256 (cloud) and ES256 (local CLI) tokens because
    verification is done server-side by GoTrue, not by decoding the JWT
    locally.
    """
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
        print(f"Token verification failed: {e}")
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
    async def _run(func, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    # ── Generic CRUD ─────────────────────────────────────────────────────

    async def create(self, table: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Insert a row. Returns the generated (or supplied) id."""
        safe = {k: v for k, v in data.items() if k not in ("created_at", "updated_at")}
        if doc_id:
            safe["id"] = doc_id

        def _ins():
            result = self.client.table(table).insert(safe).execute()
            return str(result.data[0]["id"]) if result.data else None

        return await self._run(_ins)

    async def get(self, table: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single row by id."""
        def _get():
            result = self.client.table(table).select("*").eq("id", str(doc_id)).maybe_single().execute()
            return result.data

        return await self._run(_get)

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

        return await self._run(_q)

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
