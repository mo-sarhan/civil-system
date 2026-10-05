"""Authentication, user management and login throttling."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
    ValidationError,
)
from app.core.pagination import utcnow
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_strength_errors,
    verify_password,
)
from app.models.audit import AuditAction
from app.models.user import User
from app.schemas.auth import TokenPair, UserCreate, UserOut, UserUpdate
from app.services import audit_service
from app.utils.messages import Messages


class LoginThrottle:
    """In-process sliding-window rate limiter for the login endpoint.

    Keyed by ``(ip, username)``.  For a multi-instance deployment replace this
    with a Redis-backed limiter - the interface is intentionally tiny.
    """

    def __init__(self, max_attempts: int, window_seconds: int = 60) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raise :class:`TooManyRequestsError` when the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                retry_after = int(self.window - (now - bucket[0])) + 1
                raise TooManyRequestsError(
                    f"تم تجاوز عدد المحاولات المسموح، حاول بعد {retry_after} ثانية",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """Drop every bucket; used by tests and by administrative resets."""
        with self._lock:
            self._hits.clear()


login_throttle = LoginThrottle(settings.login_rate_limit_per_minute)


class AuthService:
    """Login, refresh and user administration."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def authenticate(
        self, username: str, password: str, *, ip: str | None = None
    ) -> tuple[User, TokenPair]:
        """Validate credentials, enforce lockout and issue tokens."""
        throttle_key = f"{ip or 'unknown'}|{username.lower()}"
        login_throttle.check(throttle_key)

        user = self.db.execute(
            select(User).where(func.lower(User.username) == username.strip().lower())
        ).scalar_one_or_none()

        if user is None:
            audit_service.record(
                self.db,
                action=AuditAction.LOGIN,
                username=username,
                entity="user",
                details={"result": "unknown_user"},
                ip=ip,
                commit=True,
            )
            raise UnauthorizedError(Messages.INVALID_CREDENTIALS)

        now = utcnow()
        if user.locked_until and user.locked_until > now:
            remaining = int((user.locked_until - now).total_seconds() // 60) + 1
            raise UnauthorizedError(f"{Messages.ACCOUNT_LOCKED} (باقي {remaining} دقيقة)")

        if not verify_password(password, user.password_hash):
            user.failed_login_count = (user.failed_login_count or 0) + 1
            locked = False
            if user.failed_login_count >= settings.max_login_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                locked = True
            audit_service.record(
                self.db,
                action=AuditAction.LOGIN,
                user_id=user.id,
                username=user.username,
                entity="user",
                entity_id=user.id,
                details={
                    "result": "locked" if locked else "bad_password",
                    "attempts": user.failed_login_count,
                },
                ip=ip,
            )
            self.db.commit()
            raise UnauthorizedError(Messages.INVALID_CREDENTIALS)

        if not user.is_active:
            audit_service.record(
                self.db,
                action=AuditAction.LOGIN,
                user_id=user.id,
                username=user.username,
                entity="user",
                entity_id=user.id,
                details={"result": "inactive"},
                ip=ip,
                commit=True,
            )
            raise UnauthorizedError(Messages.ACCOUNT_DISABLED)

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        login_throttle.reset(throttle_key)

        tokens = self._issue_tokens(user)
        audit_service.record(
            self.db,
            action=AuditAction.LOGIN,
            user_id=user.id,
            username=user.username,
            entity="user",
            entity_id=user.id,
            details={"result": "success"},
            ip=ip,
        )
        self.db.commit()
        return user, tokens

    def _issue_tokens(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user.id, user.role, user.username),
            refresh_token=create_refresh_token(user.id, user.username),
            expires_in=settings.access_token_expire_minutes * 60,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a new token pair."""
        payload = decode_token(refresh_token, expected_type="refresh")
        if payload is None:
            raise UnauthorizedError(Messages.UNAUTHORIZED)
        try:
            user_id = int(payload.get("sub", ""))
        except (TypeError, ValueError):
            raise UnauthorizedError(Messages.UNAUTHORIZED) from None

        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError(Messages.ACCOUNT_DISABLED)
        return self._issue_tokens(user)

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        *,
        ip: str | None = None,
    ) -> None:
        """Self-service password change."""
        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedError(Messages.INVALID_CREDENTIALS)
        if current_password == new_password:
            raise ValidationError(Messages.PASSWORD_SAME_AS_OLD)
        errors = password_strength_errors(new_password, user.username)
        if errors:
            raise ValidationError("؛ ".join(errors))
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        audit_service.record(
            self.db,
            action=AuditAction.UPDATE,
            user_id=user.id,
            username=user.username,
            entity="user",
            entity_id=user.id,
            details={"change": "password"},
            ip=ip,
        )
        self.db.commit()

    # ------------------------------------------------------------------ #
    # User administration
    # ------------------------------------------------------------------ #
    def list_users(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        total = self.db.execute(select(func.count()).select_from(User)).scalar_one()
        users = (
            self.db.execute(
                select(User).order_by(User.id).limit(page_size).offset((page - 1) * page_size)
            )
            .scalars()
            .all()
        )
        return {
            "items": [UserOut.model_validate(user) for user in users],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def get_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError(Messages.USER_NOT_FOUND)
        return user

    def create_user(
        self, data: UserCreate, *, actor: User | None = None, ip: str | None = None
    ) -> User:
        """Create a user after validating the password policy."""
        existing = self.db.execute(
            select(func.count())
            .select_from(User)
            .where(func.lower(User.username) == data.username.lower())
        ).scalar_one()
        if existing:
            raise ConflictError(Messages.USERNAME_TAKEN)

        errors = password_strength_errors(data.password, data.username)
        if errors:
            raise ValidationError("؛ ".join(errors))

        user = User(
            username=data.username,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role,
            is_active=data.is_active,
            must_change_password=data.must_change_password,
        )
        self.db.add(user)
        self.db.flush()
        audit_service.record(
            self.db,
            action=AuditAction.CREATE,
            user_id=actor.id if actor else None,
            username=actor.username if actor else None,
            entity="user",
            entity_id=user.id,
            details={"username": user.username, "role": user.role},
            ip=ip,
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(
        self,
        user: User,
        data: UserUpdate,
        *,
        actor: User | None = None,
        ip: str | None = None,
    ) -> User:
        """Update a user's role, status or password."""
        changes: dict[str, Any] = {}
        if data.role is not None and data.role != user.role:
            if actor and actor.id == user.id:
                raise ValidationError(Messages.CANNOT_DEMOTE_SELF)
            user.role = data.role
            changes["role"] = data.role
        if data.is_active is not None and data.is_active != user.is_active:
            if actor and actor.id == user.id and not data.is_active:
                raise ValidationError(Messages.CANNOT_DELETE_SELF)
            user.is_active = data.is_active
            changes["is_active"] = data.is_active
        if data.full_name is not None:
            user.full_name = data.full_name
            changes["full_name"] = data.full_name
        if data.password:
            errors = password_strength_errors(data.password, user.username)
            if errors:
                raise ValidationError("؛ ".join(errors))
            user.password_hash = hash_password(data.password)
            user.must_change_password = True
            user.failed_login_count = 0
            user.locked_until = None
            changes["password"] = "reset"

        audit_service.record(
            self.db,
            action=AuditAction.UPDATE,
            user_id=actor.id if actor else None,
            username=actor.username if actor else None,
            entity="user",
            entity_id=user.id,
            details={"username": user.username, "changes": list(changes)},
            ip=ip,
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user: User, *, actor: User | None = None, ip: str | None = None) -> None:
        """Delete a user account."""
        if actor and actor.id == user.id:
            raise ValidationError(Messages.CANNOT_DELETE_SELF)
        user_id = user.id
        username = user.username
        self.db.delete(user)
        audit_service.record(
            self.db,
            action=AuditAction.DELETE,
            user_id=actor.id if actor else None,
            username=actor.username if actor else None,
            entity="user",
            entity_id=user_id,
            details={"username": username},
            ip=ip,
        )
        self.db.commit()

    def unlock_user(self, user: User, *, actor: User | None = None, ip: str | None = None) -> User:
        """Clear a lockout and reset the failure counter."""
        user.locked_until = None
        user.failed_login_count = 0
        audit_service.record(
            self.db,
            action=AuditAction.UPDATE,
            user_id=actor.id if actor else None,
            username=actor.username if actor else None,
            entity="user",
            entity_id=user.id,
            details={"username": user.username, "changes": ["unlock"]},
            ip=ip,
        )
        self.db.commit()
        return user
