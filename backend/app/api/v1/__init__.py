"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    duplicates,
    exports,
    imports,
    marriages,
    persons,
    relationships,
    stats,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(persons.router)
router.include_router(relationships.router)
router.include_router(marriages.router)
router.include_router(stats.router)
router.include_router(duplicates.router)
router.include_router(imports.router)
router.include_router(exports.router)
router.include_router(admin.router)

__all__ = ["router"]
