"""Simple user/auth system — JWT-based."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt

from ..config import get_settings


class UserStore:
    """Simple in-memory user store (replace with DB for production)."""

    _users: dict[str, dict] = {}

    @classmethod
    def init_default_admin(cls) -> None:
        settings = get_settings()
        if settings.default_admin_username not in cls._users:
            cls._users[settings.default_admin_username] = {
                "username": settings.default_admin_username,
                "password_hash": cls._hash_password(settings.default_admin_password),
                "role": "admin",
                "created_at": datetime.now().isoformat(),
            }

    @classmethod
    def _hash_password(cls, password: str) -> str:
        """Hash password with SHA-256 (simplified; use bcrypt for production)."""
        return hashlib.sha256(password.encode()).hexdigest()

    @classmethod
    def verify_password(cls, username: str, password: str) -> bool:
        user = cls._users.get(username)
        if not user:
            return False
        return user["password_hash"] == cls._hash_password(password)

    @classmethod
    def create_user(cls, username: str, password: str, role: str = "user") -> bool:
        if username in cls._users:
            return False
        cls._users[username] = {
            "username": username,
            "password_hash": cls._hash_password(password),
            "role": role,
            "created_at": datetime.now().isoformat(),
        }
        return True

    @classmethod
    def get_user(cls, username: str) -> Optional[dict]:
        return cls._users.get(username)

    @classmethod
    def list_users(cls) -> list[dict]:
        return [
            {"username": u["username"], "role": u["role"], "created_at": u["created_at"]}
            for u in cls._users.values()
        ]

    @classmethod
    def update_role(cls, username: str, new_role: str) -> bool:
        user = cls._users.get(username)
        if not user:
            return False
        user["role"] = new_role
        return True

    @classmethod
    def delete_user(cls, username: str) -> bool:
        if username not in cls._users:
            return False
        if username == "admin":
            return False
        del cls._users[username]
        return True


def create_token(username: str, role: str) -> str:
    """Create a JWT token for the user."""
    settings = get_settings()
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the payload."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
