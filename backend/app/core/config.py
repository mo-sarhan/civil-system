"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every value can be overridden through the environment (or a ``.env`` file).
    No secret is ever committed to the repository.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------
    app_name: str = "نظام السجل المدني وشجرة العائلة"
    app_name_en: str = "Civil Registry & Family Tree"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    timezone: str = "Africa/Cairo"

    # --- Database ------------------------------------------------------
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "civil"
    postgres_password: str = "change-me"
    postgres_db: str = "civil_registry"
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # --- Security / JWT ------------------------------------------------
    secret_key: str = "CHANGE-ME-insecure-development-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_min_length: int = 10

    # --- Login protection ----------------------------------------------
    max_login_attempts: int = 5
    login_lockout_minutes: int = 15
    login_rate_limit_per_minute: int = 10

    # --- CORS -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Business rules --------------------------------------------------
    min_parent_age_years: int = 12
    max_page_size: int = 200
    default_page_size: int = 25

    # --- Privacy ----------------------------------------------------------
    mask_national_id_roles: str = "viewer"
    audit_log_enabled: bool = True

    # --- Import ------------------------------------------------------------
    import_max_rows: int = 2_000_000
    import_chunk_size: int = 5000
    import_worker_threads: int = 2
    import_storage_dir: str = "/data/uploads"

    #: Hard ceiling for a single export request; anything larger must be
    #: narrowed with filters so a download can never exhaust server memory.
    max_export_rows: int = 500_000

    @field_validator("database_url_override", mode="before")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL."""
        if self.database_url_override:
            url = self.database_url_override
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Blocking driver URL, used by Alembic and the import worker."""
        return self.database_url.replace("postgresql+psycopg", "postgresql+psycopg")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def mask_roles(self) -> set[str]:
        return {r.strip() for r in self.mask_national_id_roles.split(",") if r.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
