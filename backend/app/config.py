"""Backend configuration shared by CORS and authentication."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


LOCAL_DEVELOPMENT_ORIGIN = "http://localhost:5173"


def configured_cors_origins() -> list[str]:
    """Return exact allowed origins; never permit wildcard origins."""
    configured = os.environ.get("SMARTQUEUE_CORS_ORIGINS")
    if configured is None:
        return [LOCAL_DEVELOPMENT_ORIGIN]

    origins = [origin.strip().rstrip("/") for origin in configured.split(",")]
    origins = [origin for origin in origins if origin]
    if "*" in origins:
        raise ValueError(
            "SMARTQUEUE_CORS_ORIGINS must list explicit origins; '*' is not allowed."
        )

    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "Each SMARTQUEUE_CORS_ORIGINS entry must be an HTTP(S) origin "
                "without a path, query, or credentials."
            )
    return origins
