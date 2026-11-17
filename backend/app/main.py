"""FastAPI application entry point for SmartQueue."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.config import configured_cors_origins
from backend.app.routers.admin import router as admin_router
from backend.app.routers.admin_analytics import router as admin_analytics_router
from backend.app.routers.admin_auth import router as admin_auth_router
from backend.app.routers.health import router as health_router
from backend.app.routers.public import router as public_router


logger = logging.getLogger(__name__)
_TRACKING_PATH_PATTERN = re.compile(
    r"^/api/public/tokens/track/[A-Za-z0-9_-]{43}$"
)


class _TrackingReferenceLogRedaction:
    """Redact bearer references before the ASGI server writes access logs."""

    def __init__(self, application: ASGIApp) -> None:
        self.application = application

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        original_path = scope.get("path", "")
        is_tracking_path = (
            scope.get("type") == "http"
            and _TRACKING_PATH_PATTERN.fullmatch(original_path) is not None
        )

        async def redact_before_response_start(message: dict[str, object]) -> None:
            if is_tracking_path and message.get("type") == "http.response.start":
                scope["path"] = "/api/public/tokens/track/REDACTED"
            await send(message)

        try:
            await self.application(scope, receive, redact_before_response_start)
        finally:
            if is_tracking_path:
                scope["path"] = "/api/public/tokens/track/REDACTED"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Keep startup side-effect free; database initialization belongs to deployment."""
    yield


app = FastAPI(
    title="SmartQueue API",
    description="Backend API for the SmartQueue queue management application.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-CSRF-Token",
        "Idempotency-Key",
    ],
)
app.add_middleware(_TrackingReferenceLogRedaction)

app.include_router(health_router)
app.include_router(public_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)
app.include_router(admin_analytics_router)
