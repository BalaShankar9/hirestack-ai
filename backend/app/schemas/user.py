"""User schemas"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class UserBase(BaseSchema):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: Optional[str] = None  # Optional if using social auth


class UserUpdate(BaseSchema):
    """Schema for updating a user."""
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase, IDMixin, TimestampMixin):
    """Schema for user response."""
    firebase_uid: str
    avatar_url: Optional[str] = None
    is_active: bool = True
    is_premium: bool = False


class UserInDB(UserResponse):
    """Schema for user in database (internal use)."""
    pass
