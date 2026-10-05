"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.api.v1 import router as api_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import engine

DESCRIPTION = """
### نظام السجل المدني وشجرة العائلة

واجهة برمجية لإدارة سجلات存在的问题 وعرض صلات القرابة بين الأفراد.

* **المصادقة**: JWT (access + refresh) مع تشفير كلمات المرور بـ argon2id.
* **الأدوار**: `admin` (كل شيء)، `editor` (إنشاء/تعديل/استيراد)، `viewer` (قراءة فقط مع إخفاء رقم القومى).
* **التدقيق**: كل عملية عرض أو تعديل أو بحث تُسجَّل في `audit_log`.
* **التوثيق**: كل المسارات موثقة في `/docs` (Swagger) و `/redoc`.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging("DEBUG" if settings.debug else "INFO")
    yield
    engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    configure_logging("DEBUG" if settings.debug else "INFO")

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "المصادقة", "description": "تسجيل الدخول، التجديد، وإدارة المستخدمين"},
            {"name": "الأشخاص", "description": "سجلات الأشخاص: إنشاء، تعديل، بحث"},
            {"name": "العلاقات", "description": "الأجداد، الأبناء، الإخوة، الأقارب، الشجرة"},
            {"name": "الزواج", "description": "تسجيلات الزواج"},
            {"name": "الإحصائيات", "description": "أرقام وإحصائيات قاعدة البيانات"},
            {"name": "المكررات", "description": "اكتشاف السجلات المكررة ودمجها"},
            {"name": "الاستيراد", "description": "رفع ملفات CSV/XLSX ومتابعة الاستيراد"},
            {"name": "التصدير", "description": "تصدير نتائج البحث"},
            {"name": "التدقيق", "description": "سجل عمليات الدخول والتعديل"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        expose_headers=["Content-Disposition", "X-Total-Count"],
        max_age=3600,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        return response

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Turn stray :class:`ValueError` raises into 400 instead of a 500.

        The validators in ``app.utils`` raise ``ValueError`` carrying an
        Arabic message, and those are always caused by bad client input.
        """
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc) or "البيانات المدخلة غير صحيحة"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Return Arabic-friendly validation errors."""
        errors = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "message": _translate(err["msg"]),
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "البيانات المدخلة غير صحيحة",
                "errors": errors,
            },
        )

    @app.get("/health", tags=["التدقيق"], summary="فحص صحة الخدمة")
    def health() -> dict:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            database = "ok"
        except Exception:  # pragma: no cover - only on DB outage
            database = "error"
        return {
            "status": "ok" if database == "ok" else "degraded",
            "database": database,
            "environment": settings.environment,
        }

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.app_name,
            "name_en": settings.app_name_en,
            "docs": "/docs",
            "api": settings.api_prefix,
        }

    return app


_PYDANTIC_MESSAGES = {
    "Field required": "حقل مطلوب",
    "Input should be a valid string": "القيمة يجب أن تكون نصاً",
    "Input should be a valid integer": "القيمة يجب أن تكون رقماً صحيحاً",
    "Input should be a valid boolean": "القيمة يجب أن تكون صحيحة أو خطأ",
    "Input should be a valid date": "القيمة يجب أن تكون تاريخاً",
    "String should have at least 1 character": "القيمة مطلوبة",
    "Input should be 'M' or 'F'": "النوع يجب أن يكون M للذكور أو F للإناث",
    "greater_than_equal": "القيمة يجب أن تكون أكبر أو مساوية",
}


def _translate(message: str) -> str:
    """Best-effort translation of Pydantic messages into Arabic."""
    for needle, arabic in _PYDANTIC_MESSAGES.items():
        if needle in message:
            return arabic
    return message


app = create_app()
