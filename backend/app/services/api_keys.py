"""
White-Label API Service
API key management, usage tracking, and rate limiting (Supabase)
"""
from typing import Optional, Dict, Any, List
import hashlib
import secrets
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class APIKeyService:
    """Service for managing API keys and usage tracking."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    @staticmethod
    def _generate_key() -> tuple:
        """Generate a new API key and return (raw_key, key_hash, key_prefix)."""
        raw_key = f"hsk_{secrets.token_urlsafe(40)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]
        return raw_key, key_hash, key_prefix

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Hash an API key for lookup."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def create_key(
        self,
        user_id: str,
        name: str = "Default Key",
        scopes: Optional[List[str]] = None,
        rate_limit: int = 100,
        expires_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new API key. Returns the raw key ONCE."""
        raw_key, key_hash, key_prefix = self._generate_key()

        expires_at = None
        if expires_days:
            from datetime import datetime, timedelta, timezone
            expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()

        record = {
            "user_id": user_id,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "name": name,
            "scopes": scopes or ["read", "write"],
            "rate_limit": rate_limit,
            "is_active": True,
            "expires_at": expires_at,
        }

        doc_id = await self.db.create(TABLES["api_keys"], record)
        logger.info("api_key_created", key_id=doc_id, prefix=key_prefix)

        key_data = await self.db.get(TABLES["api_keys"], doc_id)
        key_data["raw_key"] = raw_key  # Only time the raw key is returned
        return key_data

    async def validate_key(self, raw_key: str) -> Optional[Dict[str, Any]]:
        """Validate an API key and return the key record if valid."""
        key_hash = self._hash_key(raw_key)
        results = await self.db.query(
            TABLES["api_keys"],
            filters=[("key_hash", "==", key_hash), ("is_active", "==", True)],
            limit=1,
        )
        if not results:
            return None

        key_record = results[0]

        # Check expiry
        if key_record.get("expires_at"):
            from datetime import datetime, timezone
            expires = datetime.fromisoformat(key_record["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                return None

        # Update last_used_at
        from datetime import datetime, timezone
        await self.db.update(TABLES["api_keys"], key_record["id"], {
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        })

        return key_record

    async def track_usage(
        self,
        api_key_id: str,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int = 200,
        response_time_ms: int = 0,
    ) -> None:
        """Track API key usage."""
        await self.db.create(TABLES["api_usage"], {
            "api_key_id": api_key_id,
            "user_id": user_id,
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
        })

    async def get_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all API keys for a user (without hashes)."""
        keys = await self.db.query(
            TABLES["api_keys"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )
        # Strip sensitive data
        for k in keys:
            k.pop("key_hash", None)
        return keys

    async def get_usage_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get API usage statistics."""
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        usage = await self.db.query(
            TABLES["api_usage"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=1000,
        )

        # Filter by date in Python (PostgREST filter on timestamps can be tricky)
        recent = [u for u in usage if u.get("created_at", "") >= cutoff]

        total_requests = len(recent)
        endpoints: Dict[str, int] = {}
        total_response_time = 0
        for u in recent:
            ep = u.get("endpoint", "unknown")
            endpoints[ep] = endpoints.get(ep, 0) + 1
            total_response_time += u.get("response_time_ms", 0)

        return {
            "total_requests": total_requests,
            "avg_response_time_ms": total_response_time / total_requests if total_requests else 0,
            "endpoints": endpoints,
            "period_days": days,
        }

    async def revoke_key(self, key_id: str, user_id: str) -> bool:
        """Revoke an API key."""
        key = await self.db.get(TABLES["api_keys"], key_id)
        if not key or key.get("user_id") != user_id:
            return False
        await self.db.update(TABLES["api_keys"], key_id, {"is_active": False})
        logger.info("api_key_revoked", key_id=key_id)
        return True
