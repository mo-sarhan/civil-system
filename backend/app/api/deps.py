"""FastAPI dependencies: DB session, current user, role guards, audit context."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.session import get_db
from app.models.user import Role, User
from app.utils.messages import Messages

#: ``auto_error=False`` so we can raise our own Arabic errors.
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_client_ip(request: Request | None) -> str | None:
    """Best-effort client IP, honouring a single reverse-proxy header."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the authenticated user from the bearer token."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError(Messages.UNAUTHORIZED)
    from app.core.security import decode_token

    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise UnauthorizedError(Messages.UNAUTHORIZED)
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise UnauthorizedError(Messages.UNAUTHORIZED) from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError(Messages.ACCOUNT_DISABLED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory enforcing that the caller holds one of ``roles``."""

    def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError(Messages.FORBIDDEN)
        return user

    return _guard


#: Read access: every authenticated role.
require_reader = require_roles(*Role.ALL)
#: Write access: editor and admin.
require_writer = require_roles(Role.EDITOR, Role.ADMIN)
#: Import access: editor and admin.
require_importer = require_roles(Role.EDITOR, Role.ADMIN)
#: Administrative access.
require_admin = require_roles(Role.ADMIN)

ReaderUser = Annotated[User, Depends(require_reader)]
WriterUser = Annotated[User, Depends(require_writer)]
ImporterUser = Annotated[User, Depends(require_importer)]
AdminUser = Annotated[User, Depends(require_admin)]
