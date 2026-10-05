"""Application exception types mapped to HTTP responses."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base class for domain errors carrying an Arabic message."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "حدث خطأ غير متوقع"

    def __init__(
        self,
        detail: str | None = None,
        *,
        status_code: int | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code or self.status_code,
            detail=detail or self.default_detail,
            headers=headers,
        )
        self.errors = errors


class ValidationError(AppError):
    """Invalid input (400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "البيانات المدخلة غير صحيحة"


class NotFoundError(AppError):
    """Resource missing (404)."""

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "السجل غير موجود"


class ConflictError(AppError):
    """Uniqueness / state conflict (409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "تعارض في البيانات"


class UnauthorizedError(AppError):
    """Missing or invalid credentials (401)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "يجب تسجيل الدخول للمتابعة"


class ForbiddenError(AppError):
    """Authenticated but lacking the required role (403)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "لا تملك الصلاحية اللازمة لتنفيذ هذا الإجراء"


class PayloadTooLargeError(AppError):
    """File or query too large (413)."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "حجم البيانات كبير جداً"


class TooManyRequestsError(AppError):
    """Rate limited (429)."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "عدد المحاولات كبير، يرجى المحاولة لاحقاً"
