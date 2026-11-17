"""Authenticated administrator endpoints for counters and queue operations."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from backend.app.routers.admin_auth import require_admin_session
from backend.app.security import (
    AdminSession,
    validate_csrf_token,
    validate_request_origin,
)
from database import db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin operations"])
TokenStatus = Literal["Waiting", "Serving", "Served"]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CounterCreateRequest(StrictRequestModel):
    counter_name: str = Field(min_length=1, max_length=100)
    service_type: str
    active_counters: StrictInt = Field(ge=1, le=5)
    avg_service_time: float = Field(ge=1, le=15)

    @field_validator("counter_name")
    @classmethod
    def normalize_counter_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Counter name must not be blank.")
        return normalized

    @field_validator("service_type")
    @classmethod
    def validate_service_type(cls, value: str) -> str:
        if value not in db.SERVICE_TYPES:
            raise ValueError("Unsupported service type.")
        return value


class CounterUpdateRequest(StrictRequestModel):
    people_waiting: StrictInt = Field(ge=0, le=50)
    active_counters: StrictInt = Field(ge=1, le=5)
    avg_service_time: float = Field(ge=1, le=15)
    is_active: StrictBool


class CounterStatusRequest(StrictRequestModel):
    is_active: StrictBool


class CounterResponse(BaseModel):
    counter_id: int
    counter_name: str
    service_type: str
    is_active: bool
    people_waiting: int
    active_counters: int
    avg_service_time: float


class CounterListResponse(BaseModel):
    counters: list[CounterResponse]


class TokenResponse(BaseModel):
    token_id: int
    token_number: str
    service_type: str
    counter_name: str
    status: TokenStatus
    created_at: str


class TokenListResponse(BaseModel):
    tokens: list[TokenResponse]


class TokenStatusRequest(StrictRequestModel):
    status: TokenStatus


class TokenStatusResponse(BaseModel):
    token_id: int
    status: TokenStatus


class StatisticsResponse(BaseModel):
    waiting_count: int
    serving_count: int
    currently_served_count: int
    historically_served_count: int
    active_counter_count: int


def _database_unavailable(exc: Exception) -> HTTPException:
    logger.warning("SmartQueue admin database operation failed: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable",
    )


def _require_csrf(request: Request, session: AdminSession) -> None:
    validate_request_origin(request)
    validate_csrf_token(session, request.headers.get("x-csrf-token"))


def _counter_response(counter: dict[str, object]) -> CounterResponse:
    return CounterResponse(
        counter_id=int(counter["counter_id"]),
        counter_name=str(counter["counter_name"]),
        service_type=str(counter["service_type"]),
        is_active=bool(counter["is_active"]),
        people_waiting=int(counter["people_waiting"] or 0),
        active_counters=int(counter["active_counters"]),
        avg_service_time=float(counter["avg_service_time"]),
    )


@router.get("/counters", response_model=CounterListResponse)
def list_counters(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> CounterListResponse:
    """List active and inactive counters for administrator management."""
    try:
        counters = db.get_all_counters()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return CounterListResponse(
        counters=[_counter_response(counter) for counter in counters]
    )


@router.post(
    "/counters",
    response_model=CounterResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_counter(
    payload: CounterCreateRequest,
    request: Request,
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> CounterResponse:
    """Create a counter using the existing database operation."""
    _require_csrf(request, session)
    try:
        counter_id = db.add_counter(
            payload.counter_name,
            payload.service_type,
            payload.active_counters,
            payload.avg_service_time,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid counter settings",
        ) from exc
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc

    return CounterResponse(
        counter_id=counter_id,
        counter_name=payload.counter_name,
        service_type=payload.service_type,
        is_active=True,
        people_waiting=0,
        active_counters=payload.active_counters,
        avg_service_time=payload.avg_service_time,
    )


@router.put("/counters/{counter_id}", response_model=CounterResponse)
def update_counter(
    payload: CounterUpdateRequest,
    request: Request,
    counter_id: Annotated[int, Path(gt=0)],
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> CounterResponse:
    """Update mutable counter settings; name and service remain read-only."""
    _require_csrf(request, session)
    try:
        updated = db.update_counter(
            counter_id,
            payload.people_waiting,
            payload.active_counters,
            payload.avg_service_time,
            payload.is_active,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter not found",
            )
        counter = db.get_counter_by_id(counter_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid counter settings",
        ) from exc
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    if counter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    return _counter_response(counter)


@router.patch(
    "/counters/{counter_id}/status",
    response_model=CounterResponse,
)
def set_counter_status(
    payload: CounterStatusRequest,
    request: Request,
    counter_id: Annotated[int, Path(gt=0)],
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> CounterResponse:
    """Activate or deactivate a counter without deleting its record."""
    _require_csrf(request, session)
    try:
        counter = db.get_counter_by_id(counter_id)
        if counter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter not found",
            )
        updated = db.update_counter(
            counter_id,
            int(counter["people_waiting"] or 0),
            int(counter["active_counters"]),
            float(counter["avg_service_time"]),
            payload.is_active,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter not found",
            )
        updated_counter = db.get_counter_by_id(counter_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid counter settings",
        ) from exc
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    if updated_counter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    return _counter_response(updated_counter)


@router.get("/tokens", response_model=TokenListResponse)
def list_tokens(
    _: Annotated[AdminSession, Depends(require_admin_session)],
    token_status: Annotated[TokenStatus | None, Query(alias="status")] = None,
    service_type: Annotated[str | None, Query()] = None,
) -> TokenListResponse:
    """List queue tokens with optional status and service filters."""
    if service_type is not None and service_type not in db.SERVICE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported service type",
        )
    try:
        tokens = db.get_queue_tokens(
            status=token_status,
            service_type=service_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid token filters",
        ) from exc
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return TokenListResponse(tokens=[TokenResponse(**token) for token in tokens])


@router.patch(
    "/tokens/{token_id}/status",
    response_model=TokenStatusResponse,
)
def set_token_status(
    payload: TokenStatusRequest,
    request: Request,
    token_id: Annotated[int, Path(gt=0)],
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> TokenStatusResponse:
    """Advance a token according to the existing administrator queue workflow."""
    _require_csrf(request, session)
    try:
        token = db.get_token_by_id(token_id)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )
        allowed_transitions = {
            "Waiting": {"Serving", "Served"},
            "Serving": {"Served"},
            "Served": set(),
        }
        if payload.status not in allowed_transitions.get(token["status"], set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Token status transition is not allowed",
            )
        updated = db.update_token_status(token_id, payload.status)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid token status",
        ) from exc
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )
    return TokenStatusResponse(token_id=token_id, status=payload.status)


@router.get("/statistics", response_model=StatisticsResponse)
def get_statistics(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> StatisticsResponse:
    """Return current queue counts and the separately tracked served history."""
    try:
        statistics = db.get_queue_statistics()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return StatisticsResponse(
        waiting_count=int(statistics["waiting_tokens"]),
        serving_count=int(statistics["serving_tokens"]),
        currently_served_count=int(statistics["served_tokens"]),
        historically_served_count=int(statistics["historically_served_tokens"]),
        active_counter_count=int(statistics["active_counters"]),
    )
