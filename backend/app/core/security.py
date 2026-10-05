"""Password hashing (argon2) and JWT creation/verification."""

from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import settings

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an argon2 hash."""
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses outdated parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def password_strength_errors(password: str, username: str | None = None) -> list[str]:
    """Return a list of Arabic problems with a candidate password (empty = OK)."""
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"كلمة المرور يجب أن تكون {settings.password_min_length} حرفاً على الأقل")
    if not any(c.isupper() for c in password):
        errors.append("كلمة المرور يجب أن تحتوي على حرف كبير (A-Z)")
    if not any(c.islower() for c in password):
        errors.append("كلمة المرور يجب أن تحتوي على حرف صغير (a-z)")
    if not any(c.isdigit() for c in password):
        errors.append("كلمة المرور يجب أن تحتوي على رقم (0-9)")
    if not any(not c.isalnum() for c in password):
        errors.append("كلمة المرور يجب أن تحتوي على رمز خاص")
    if username and username.lower() in password.lower():
        errors.append("كلمة المرور يجب ألا تحتوي على اسم المستخدم")
    return errors


def generate_password(length: int = 16) -> str:
    """Generate a strong random password that satisfies :func:`password_strength_errors`."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if not password_strength_errors(password):
            return password


def hash_token(token: str) -> str:
    """Hash a refresh token for at-rest storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _create_token(
    subject: str, token_type: TokenType, expires_delta: timedelta, **claims: Any
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str, username: str) -> str:
    """Short-lived access token."""
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        role=role,
        username=username,
    )


def create_refresh_token(user_id: int, username: str) -> str:
    """Long-lived refresh token."""
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        username=username,
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any] | None:
    """Decode and validate a JWT; returns ``None`` when invalid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload
