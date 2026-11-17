"""Admin login, session verification, and logout endpoints."""

from __future__ import annotations

import logging
import time
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import db
from backend.app.security import (
    AdminSession,
    SESSION_DURATION_SECONDS,
    SESSION_COOKIE_LOCAL,
    SESSION_COOKIE_SECURE,
    clear_login_failures,
    cookie_is_secure,
    cookie_same_site,
    create_admin_session,
    login_rate_limit_remaining,
    record_login_failure,
    revoke_admin_session,
    session_cookie_name,
    validate_admin_session,
    validate_csrf_token,
    validate_request_origin,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/auth", tags=["admin authentication"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Username must not be blank.")
        return normalized


class LoginResponse(BaseModel):
    authenticated: Literal[True]
    username: str
    csrf_token: str
    expires_in: int


class SessionResponse(LoginResponse):
    pass


class LogoutResponse(BaseModel):
    authenticated: Literal[False]


def require_admin_session(
    request: Request,
    session_cookie: Annotated[
        str | None,
        Cookie(
            alias=SESSION_COOKIE_SECURE,
        ),
    ] = None,
) -> AdminSession:
    """Reusable dependency that verifies the signed session on every request."""
    cookie_value = session_cookie or request.cookies.get(SESSION_COOKIE_LOCAL)
    return validate_admin_session(cookie_value)


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def _set_session_cookie(
    response: Response,
    request: Request,
    cookie_value: str,
) -> None:
    response.set_cookie(
        key=session_cookie_name(request),
        value=cookie_value,
        max_age=SESSION_DURATION_SECONDS,
        httponly=True,
        secure=cookie_is_secure(request),
        samesite=cookie_same_site(request),
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    for cookie_name in {SESSION_COOKIE_LOCAL, SESSION_COOKIE_SECURE}:
        response.delete_cookie(
            key=cookie_name,
            path="/",
            secure=cookie_name == SESSION_COOKIE_SECURE,
            httponly=True,
            samesite="none" if cookie_name == SESSION_COOKIE_SECURE else "lax",
        )


@router.post("/login", response_model=LoginResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Authenticate an administrator and issue an HttpOnly signed session cookie."""
    validate_request_origin(request)
    client_key = _client_key(request)
    retry_after = login_rate_limit_remaining(client_key)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        authenticated = db.authenticate_admin(
            credentials.username,
            credentials.password,
        )
    except (db.DatabaseOperationError, OSError) as exc:
        logger.warning("Admin authentication database operation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc

    if not authenticated:
        record_login_failure(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Cookie"},
        )

    clear_login_failures(client_key)
    session, cookie_value = create_admin_session(credentials.username)
    _set_session_cookie(response, request, cookie_value)
    return LoginResponse(
        authenticated=True,
        username=session.username,
        csrf_token=session.csrf_token,
        expires_in=SESSION_DURATION_SECONDS,
    )


@router.get("/session", response_model=SessionResponse)
def get_session(
    request: Request,
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> SessionResponse:
    """Return safe session details after validating the cookie server-side."""
    validate_request_origin(request)
    remaining = max(0, session.expires_at - int(time.time()))
    return SessionResponse(
        authenticated=True,
        username=session.username,
        csrf_token=session.csrf_token,
        expires_in=int(remaining),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> LogoutResponse:
    """Revoke the current session and clear its browser cookie."""
    validate_request_origin(request)
    validate_csrf_token(session, request.headers.get("x-csrf-token"))
    revoke_admin_session(session.session_id)
    _clear_session_cookies(response)
    return LogoutResponse(authenticated=False)
