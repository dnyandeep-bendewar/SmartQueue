"""Health and database-readiness endpoints."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from database import db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])


class HealthResponse(BaseModel):
    """Minimal status response that contains no deployment configuration."""

    status: Literal["ok"]


@router.get("", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report that the API process is responsive."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def readiness_check() -> HealthResponse:
    """Verify access to the already-existing database without initializing it."""
    try:
        db.check_database()
    except (db.DatabaseOperationError, OSError) as exc:
        logger.warning("SmartQueue database readiness check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    return HealthResponse(status="ok")
