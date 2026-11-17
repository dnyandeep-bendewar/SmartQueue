"""Signed admin sessions, origin/CSRF checks, and login throttling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass
from typing import Final

from fastapi import HTTPException, Request, status

from backend.app.config import configured_cors_origins


SESSION_COOKIE_LOCAL: Final = "smartqueue_session"
SESSION_COOKIE_SECURE: Final = "__Host-smartqueue_session"
SESSION_DURATION_SECONDS: Final = 8 * 60 * 60
LOGIN_WINDOW_SECONDS: Final = 15 * 60
LOGIN_MAX_FAILURES: Final = 5
_LOGIN_BUCKET_LIMIT: Final = 10_000
_SESSION_LIMIT: Final = 10_000

_lock = threading.RLock()
_sessions: OrderedDict[str, tuple[str, int, str]] = OrderedDict()
_login_failures: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class AdminSession:
    username: str
    session_id: str
    expires_at: int
    csrf_token: str


def session_cookie_name(request: Request) -> str:
    """Use a __Host- cookie for HTTPS and a local-only name for HTTP development."""
    return SESSION_COOKIE_SECURE if cookie_is_secure(request) else SESSION_COOKIE_LOCAL


def cookie_is_secure(request: Request) -> bool:
    """Never disable Secure in production or for HTTPS requests."""
    deployment = os.environ.get("SMARTQUEUE_ENV", "").strip().lower()
    return request.url.scheme == "https" or deployment in {"prod", "production"}


def cookie_same_site(request: Request) -> str:
    """Allow cross-site production frontends only with Secure cookies."""
    return "none" if cookie_is_secure(request) else "lax"


def validate_request_origin(request: Request) -> None:
    """Require the browser Origin to exactly match a configured frontend origin."""
    origin = request.headers.get("origin")
    if origin is None or origin not in configured_cors_origins():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed",
        )


def _session_signing_secret() -> bytes:
    secret = os.environ.get("SMARTQUEUE_SESSION_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return secret.encode("utf-8")


def _encode_segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _prune_sessions(now: int) -> None:
    expired = [
        session_id
        for session_id, (_, expires_at, _) in _sessions.items()
        if expires_at <= now
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def create_admin_session(username: str) -> tuple[AdminSession, str]:
    """Create a signed session cookie containing no password or password hash."""
    now = int(time.time())
    expires_at = now + SESSION_DURATION_SECONDS
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session = AdminSession(
        username=username,
        session_id=session_id,
        expires_at=expires_at,
        csrf_token=csrf_token,
    )
    payload = {
        "sub": username,
        "sid": session_id,
        "iat": now,
        "exp": expires_at,
    }
    encoded_payload = _encode_segment(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _session_signing_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    cookie_value = f"{encoded_payload}.{_encode_segment(signature)}"

    with _lock:
        _prune_sessions(now)
        _sessions[session_id] = (username, expires_at, csrf_token)
        _sessions.move_to_end(session_id)
        while len(_sessions) > _SESSION_LIMIT:
            _sessions.popitem(last=False)

    return session, cookie_value


def validate_admin_session(cookie_value: str | None) -> AdminSession:
    """Verify cookie signature, expiry, and server-side revocation state."""
    failure = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Cookie"},
    )
    if not cookie_value or cookie_value.count(".") != 1:
        raise failure

    encoded_payload, encoded_signature = cookie_value.split(".", maxsplit=1)
    try:
        supplied_signature = _decode_segment(encoded_signature)
        expected_signature = hmac.new(
            _session_signing_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise failure
        payload = json.loads(_decode_segment(encoded_payload))
        username = payload["sub"]
        session_id = payload["sid"]
        expires_at = payload["exp"]
        issued_at = payload["iat"]
        if (
            not isinstance(username, str)
            or not username
            or not isinstance(session_id, str)
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(issued_at, bool)
            or issued_at > int(time.time())
            or expires_at - issued_at != SESSION_DURATION_SECONDS
        ):
            raise failure
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise failure from None

    now = int(time.time())
    with _lock:
        _prune_sessions(now)
        active = _sessions.get(session_id)
        if (
            expires_at <= now
            or active is None
            or active[0] != username
            or active[1] != expires_at
        ):
            raise failure
        csrf_token = active[2]
        _sessions.move_to_end(session_id)

    return AdminSession(
        username=username,
        session_id=session_id,
        expires_at=expires_at,
        csrf_token=csrf_token,
    )


def revoke_admin_session(session_id: str) -> None:
    """Invalidate a session immediately in this backend process."""
    with _lock:
        _sessions.pop(session_id, None)


def validate_csrf_token(session: AdminSession, supplied_token: str | None) -> None:
    """Require the CSRF token bound to the signed session."""
    if supplied_token is None or not hmac.compare_digest(
        session.csrf_token,
        supplied_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


def login_rate_limit_remaining(client_key: str) -> int:
    """Return seconds until retry is permitted, or zero when not limited."""
    now = time.monotonic()
    with _lock:
        for key in list(_login_failures):
            failures = _login_failures[key]
            while failures and now - failures[0] >= LOGIN_WINDOW_SECONDS:
                failures.popleft()
            if not failures:
                _login_failures.pop(key, None)
        failures = _login_failures[client_key]
        if len(failures) < LOGIN_MAX_FAILURES:
            return 0
        return max(1, int(LOGIN_WINDOW_SECONDS - (now - failures[0])))


def record_login_failure(client_key: str) -> None:
    """Record a failed login attempt and bound limiter memory."""
    now = time.monotonic()
    with _lock:
        failures = _login_failures[client_key]
        while failures and now - failures[0] >= LOGIN_WINDOW_SECONDS:
            failures.popleft()
        failures.append(now)
        while len(_login_failures) > _LOGIN_BUCKET_LIMIT:
            oldest_key = min(
                _login_failures,
                key=lambda key: _login_failures[key][0] if _login_failures[key] else now,
            )
            _login_failures.pop(oldest_key, None)


def clear_login_failures(client_key: str) -> None:
    """Clear the failure bucket after successful authentication."""
    with _lock:
        _login_failures.pop(client_key, None)
