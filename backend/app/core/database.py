"""
HireStack AI - Database Module
Firebase Firestore integration for data storage
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import os

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from google.cloud import firestore as gcfirestore
from google.cloud.firestore_v1 import FieldFilter
from google.api_core.exceptions import NotFound
from google.oauth2 import service_account

from app.core.config import settings


# Firebase Admin SDK initialization
_firebase_app = None
_firestore_client = None


def init_firebase():
    """Initialize Firebase Admin SDK."""
    global _firebase_app, _firestore_client

    if _firebase_app is not None and _firestore_client is not None:
        return _firestore_client

    cred_path = settings.firebase_credentials_path
    resolved_cred_path = None
    if cred_path:
        resolved_cred_path = cred_path
        if not os.path.isabs(resolved_cred_path):
            resolved_cred_path = os.path.join(os.getcwd(), resolved_cred_path)

    try:
        # Check if already initialized
        _firebase_app = firebase_admin.get_app()
    except ValueError:
        # Not initialized yet, initialize now
        if resolved_cred_path and os.path.exists(resolved_cred_path):
            cred = credentials.Certificate(resolved_cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
        else:
            # Try default credentials (for cloud environments)
            _firebase_app = firebase_admin.initialize_app(options={
                'projectId': settings.firebase_project_id
            })

    gcp_creds = None
    if resolved_cred_path and os.path.exists(resolved_cred_path):
        gcp_creds = service_account.Credentials.from_service_account_file(resolved_cred_path)

    # Firestore database ID handling:
    # - New Firestore multi-database defaults often use `default` (no parentheses)
    # - Older projects use `(default)`
    # We try the configured value first, then fall back.
    candidates: List[str] = []
    if getattr(settings, "firebase_database_id", None):
        candidates.append(settings.firebase_database_id)
    candidates.extend(["default", "(default)"])

    last_err: Optional[Exception] = None
    chosen: Optional[gcfirestore.Client] = None
    for db_id in [c for c in candidates if c]:
        try:
            chosen = gcfirestore.Client(
                project=settings.firebase_project_id,
                credentials=gcp_creds,
                database=db_id,
            )
            # Lightweight probe; if the database doesn't exist we'll get a NotFound.
            chosen.collection("_health").document("ping").get(timeout=2)
            _firestore_client = chosen
            return _firestore_client
        except NotFound as e:
            last_err = e
            chosen = None
            continue
        except Exception as e:
            # Don't fail startup for transient/network issues; keep the client and let endpoints surface errors.
            last_err = e
            _firestore_client = chosen
            return _firestore_client

    # If we couldn't find a working DB id, still create a client so the app can boot and health can report errors.
    _firestore_client = gcfirestore.Client(
        project=settings.firebase_project_id,
        credentials=gcp_creds,
        database=candidates[0] if candidates else "default",
    )
    return _firestore_client


def get_db():
    """Get Firestore client instance."""
    global _firestore_client
    if _firestore_client is None:
        init_firebase()
    return _firestore_client


def verify_firebase_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Firebase ID token and return the decoded token.
    Returns None if verification fails.
    """
    init_firebase()
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None


def get_firebase_user(uid: str) -> Optional[Dict[str, Any]]:
    """Get Firebase user by UID."""
    init_firebase()
    try:
        user = firebase_auth.get_user(uid)
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'photo_url': user.photo_url,
            'email_verified': user.email_verified,
        }
    except Exception:
        return None


# Firestore Collection Names
COLLECTIONS = {
    'users': 'users',
    'profiles': 'profiles',
    'jobs': 'job_descriptions',
    'benchmarks': 'benchmarks',
    'gap_reports': 'gap_reports',
    'roadmaps': 'roadmaps',
    'projects': 'projects',
    'documents': 'documents',
    'exports': 'exports',
    'analytics': 'analytics',
}


class FirestoreDB:
    """Helper class for Firestore operations."""

    def __init__(self):
        self.db = get_db()

    # Generic CRUD operations
    async def create(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Create a document in a collection."""
        data['created_at'] = datetime.utcnow()
        data['updated_at'] = datetime.utcnow()

        if doc_id:
            self.db.collection(collection).document(doc_id).set(data)
            return doc_id
        else:
            doc_ref = self.db.collection(collection).add(data)
            return doc_ref[1].id

    async def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        doc = self.db.collection(collection).document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None

    async def update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update a document."""
        data['updated_at'] = datetime.utcnow()
        self.db.collection(collection).document(doc_id).update(data)
        return True

    async def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document."""
        self.db.collection(collection).document(doc_id).delete()
        return True

    async def query(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        order_direction: str = 'DESCENDING',
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents with optional filters."""
        query = self.db.collection(collection)

        if filters:
            for field, op, value in filters:
                query = query.where(filter=FieldFilter(field, op, value))

        if order_by:
            direction = gcfirestore.Query.DESCENDING if order_direction == 'DESCENDING' else gcfirestore.Query.ASCENDING
            query = query.order_by(order_by, direction=direction)

        if limit:
            query = query.limit(limit)

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)

        return results

    # User operations
    async def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """Get user by Firebase UID."""
        users = await self.query(
            COLLECTIONS['users'],
            filters=[('firebase_uid', '==', firebase_uid)],
            limit=1
        )
        return users[0] if users else None

    async def get_or_create_user(
        self,
        firebase_uid: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing user or create new one."""
        user = await self.get_user_by_firebase_uid(firebase_uid)

        if not user:
            user_data = {
                'firebase_uid': firebase_uid,
                'email': email,
                'full_name': full_name,
                'avatar_url': avatar_url,
                'is_active': True,
                'is_premium': False,
            }
            doc_id = await self.create(COLLECTIONS['users'], user_data)
            user = await self.get(COLLECTIONS['users'], doc_id)

        return user


# Global instance
firestore_db = FirestoreDB()


def get_firestore_db() -> FirestoreDB:
    """Get FirestoreDB instance."""
    return firestore_db
