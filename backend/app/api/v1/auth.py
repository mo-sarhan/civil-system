"""Auth and user-management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import (
    AdminUser,
    CurrentUser,
    DbSession,
    ReaderUser,
    get_client_ip,
)
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.auth_service import AuthService

router = APIRouter(tags=["المصادقة"])


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="تسجيل الدخول",
    description="يعيد توكن وصول قصير العمر وتوكن تجديد. يتم قفل الحساب بعد عدة محاولات فاشلة.",
)
def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    service = AuthService(db)
    user, tokens = service.authenticate(
        payload.username, payload.password, ip=get_client_ip(request)
    )
    return LoginResponse(**tokens.model_dump(), user=UserOut.model_validate(user))


@router.post(
    "/auth/refresh",
    response_model=TokenPair,
    summary="تجديد التوكن",
)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    return AuthService(db).refresh(payload.refresh_token)


@router.get("/auth/me", response_model=UserOut, summary="بيانات المستخدم الحالي")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post(
    "/auth/change-password",
    summary="تغيير كلمة المرور",
    description="يجب استدعاؤها عند must_change_password = true.",
)
def change_password(
    payload: PasswordChange, request: Request, user: CurrentUser, db: DbSession
) -> dict[str, str]:
    AuthService(db).change_password(
        user, payload.current_password, payload.new_password, ip=get_client_ip(request)
    )
    return {"message": "تم تغيير كلمة المرور بنجاح"}


# --------------------------------------------------------------------------- #
# User administration (admin only)
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=dict, summary="قائمة المستخدمين")
def list_users(db: DbSession, admin: AdminUser, page: int = 1, page_size: int = 100) -> dict:
    return AuthService(db).list_users(page=page, page_size=page_size)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="إنشاء مستخدم",
)
def create_user(payload: UserCreate, request: Request, db: DbSession, admin: AdminUser) -> UserOut:
    user = AuthService(db).create_user(payload, actor=admin, ip=get_client_ip(request))
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut, summary="تعديل مستخدم")
def update_user(
    user_id: int, payload: UserUpdate, request: Request, db: DbSession, admin: AdminUser
) -> UserOut:
    service = AuthService(db)
    user = service.get_user(user_id)
    return UserOut.model_validate(
        service.update_user(user, payload, actor=admin, ip=get_client_ip(request))
    )


@router.delete("/users/{user_id}", summary="حذف مستخدم")
def delete_user(user_id: int, request: Request, db: DbSession, admin: AdminUser) -> dict[str, str]:
    service = AuthService(db)
    user = service.get_user(user_id)
    service.delete_user(user, actor=admin, ip=get_client_ip(request))
    return {"message": "تم حذف المستخدم"}


@router.post("/users/{user_id}/unlock", response_model=UserOut, summary="فك قفل حساب")
def unlock_user(user_id: int, request: Request, db: DbSession, admin: AdminUser) -> UserOut:
    service = AuthService(db)
    user = service.get_user(user_id)
    return UserOut.model_validate(service.unlock_user(user, actor=admin, ip=get_client_ip(request)))


@router.get("/config", summary="إعدادات عامة يحتاجها الواجهة")
def public_config(_user: ReaderUser) -> dict:
    """Non-sensitive runtime configuration for the UI."""
    return {
        "min_parent_age_years": settings.min_parent_age_years,
        "masked_roles": sorted(settings.mask_roles),
        "max_page_size": settings.max_page_size,
        "default_page_size": settings.default_page_size,
        "password_min_length": settings.password_min_length,
        "import_max_rows": settings.import_max_rows,
    }
