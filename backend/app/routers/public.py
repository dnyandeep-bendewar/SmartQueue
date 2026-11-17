"""Public visitor endpoints for services, estimates, and secure token tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import db
from models.predict import VALID_SERVICE_TYPES, predict_waiting_time


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public", tags=["public visitor"])

_TRACKING_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
_IDEMPOTENCY_MAX_ENTRIES = 4096
_idempotency_lock = threading.Lock()
_idempotency_records: OrderedDict[
    str,
    tuple[float, str, "TokenIssueResponse"],
] = OrderedDict()


class StrictRequestModel(BaseModel):
    """Reject unexpected request fields rather than silently ignoring them."""

    model_config = ConfigDict(extra="forbid")


class ServicesResponse(BaseModel):
    services: list[str]


class CounterPrediction(BaseModel):
    counter_id: int
    predicted_wait_minutes: float | None
    available: bool
    error_code: Literal["prediction_unavailable"] | None = None


class PublicCounter(BaseModel):
    counter_id: int
    counter_name: str
    service_type: str
    people_waiting: int
    active_counters: int
    avg_service_time: float
    prediction: CounterPrediction


class CounterListResponse(BaseModel):
    counters: list[PublicCounter]
    recommended_counter_id: int | None


class CounterPredictionResponse(CounterPrediction):
    pass


class TokenIssueRequest(StrictRequestModel):
    counter_id: int = Field(gt=0, strict=True)
    visitor_name: str | None = Field(default=None, max_length=100)

    @field_validator("visitor_name")
    @classmethod
    def normalize_visitor_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TokenIssueResponse(BaseModel):
    token_number: str
    tracking_reference: str
    status: Literal["Waiting"]
    queue_position: int | None
    idempotent_replay: bool = False


class TrackedTokenResponse(BaseModel):
    token_number: str
    service_type: str
    counter_name: str
    status: Literal["Waiting", "Serving", "Served"]
    created_at: str
    queue_position: int | None


def _database_unavailable(exc: Exception) -> HTTPException:
    logger.warning("SmartQueue public database operation failed: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable",
    )


def _predict_counter(counter: dict[str, Any], now: datetime) -> float:
    """Apply the existing visitor prediction hour rule and model validation."""
    prediction_hour = min(max(now.hour, 9), 18)
    return predict_waiting_time(
        people_waiting=counter["people_waiting"],
        active_counters=counter["active_counters"],
        avg_service_time=counter["avg_service_time"],
        hour=prediction_hour,
        day_of_week=now.weekday(),
        service_type=str(counter["service_type"]),
    )


def _counter_prediction(counter: dict[str, Any]) -> CounterPrediction:
    """Compute one counter estimate without allowing a failure to abort a list."""
    counter_id = int(counter["counter_id"])
    try:
        value = _predict_counter(counter, datetime.now().astimezone())
        if not math.isfinite(value) or value < 0:
            raise ValueError("Prediction was not a finite non-negative value.")
    except Exception as exc:
        logger.warning(
            "Waiting-time prediction unavailable for counter %s (%s)",
            counter_id,
            type(exc).__name__,
        )
        return CounterPrediction(
            counter_id=counter_id,
            predicted_wait_minutes=None,
            available=False,
            error_code="prediction_unavailable",
        )

    return CounterPrediction(
        counter_id=counter_id,
        predicted_wait_minutes=value,
        available=True,
    )


def _idempotency_fingerprint(request: TokenIssueRequest) -> str:
    body = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _cached_token_issue(
    key: str,
    fingerprint: str,
) -> TokenIssueResponse | None:
    now = time.monotonic()
    expired_keys = [
        stored_key
        for stored_key, (created_at, _, _) in _idempotency_records.items()
        if now - created_at >= _IDEMPOTENCY_TTL_SECONDS
    ]
    for expired_key in expired_keys:
        _idempotency_records.pop(expired_key, None)

    record = _idempotency_records.get(key)
    if record is None:
        return None
    _, stored_fingerprint, response = record
    if stored_fingerprint != fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for a different request",
        )
    _idempotency_records.move_to_end(key)
    return response.model_copy(update={"idempotent_replay": True})


def _remember_token_issue(
    key: str,
    fingerprint: str,
    response: TokenIssueResponse,
) -> None:
    _idempotency_records[key] = (time.monotonic(), fingerprint, response)
    _idempotency_records.move_to_end(key)
    while len(_idempotency_records) > _IDEMPOTENCY_MAX_ENTRIES:
        _idempotency_records.popitem(last=False)


@router.get("/services", response_model=ServicesResponse)
def list_services() -> ServicesResponse:
    """List the service types supported by the saved model."""
    return ServicesResponse(services=sorted(VALID_SERVICE_TYPES))


@router.get("/counters", response_model=CounterListResponse)
def list_active_counters(
    service_type: Annotated[str | None, Query()] = None,
) -> CounterListResponse:
    """List active visitor counters with independent estimates and a safe recommendation."""
    if service_type is not None and service_type not in VALID_SERVICE_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Unsupported service type",
        )
    try:
        counters = db.get_all_counters()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc

    matching = [
        counter
        for counter in counters
        if bool(counter.get("is_active"))
        and (service_type is None or counter.get("service_type") == service_type)
    ]
    results: list[PublicCounter] = []
    predictions: dict[int, float] = {}
    for counter in matching:
        prediction = _counter_prediction(counter)
        if prediction.available and prediction.predicted_wait_minutes is not None:
            predictions[prediction.counter_id] = prediction.predicted_wait_minutes
        results.append(
            PublicCounter(
                counter_id=int(counter["counter_id"]),
                counter_name=str(counter["counter_name"]),
                service_type=str(counter["service_type"]),
                people_waiting=int(counter["people_waiting"] or 0),
                active_counters=int(counter["active_counters"]),
                avg_service_time=float(counter["avg_service_time"]),
                prediction=prediction,
            )
        )

    recommendation: int | None = None
    if matching and len(predictions) == len(matching):
        recommendation = min(predictions, key=predictions.__getitem__)
    return CounterListResponse(
        counters=results,
        recommended_counter_id=recommendation,
    )


@router.get(
    "/counters/{counter_id}/prediction",
    response_model=CounterPredictionResponse,
)
def predict_counter(
    counter_id: Annotated[int, Path(gt=0)],
) -> CounterPredictionResponse:
    """Return one active counter estimate, or an explicit unavailable result."""
    try:
        counter = db.get_counter_by_id(counter_id)
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    if counter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    if not bool(counter.get("is_active")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Counter is inactive",
        )
    prediction = _counter_prediction(counter)
    return CounterPredictionResponse(**prediction.model_dump())


@router.post(
    "/tokens",
    response_model=TokenIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_token(
    request: TokenIssueRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[A-Za-z0-9._~-]+$",
        ),
    ],
) -> TokenIssueResponse:
    """Issue a token with retry protection scoped to this API process."""
    fingerprint = _idempotency_fingerprint(request)
    with _idempotency_lock:
        replay = _cached_token_issue(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        try:
            counter = db.get_counter_by_id(request.counter_id)
        except (db.DatabaseOperationError, OSError) as exc:
            raise _database_unavailable(exc) from exc
        if counter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter not found",
            )
        if not bool(counter.get("is_active")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Counter is inactive",
            )

        if request.visitor_name is not None:
            try:
                duplicate_exists = db.has_active_token_for_visitor(
                    request.counter_id,
                    request.visitor_name,
                )
            except (db.DatabaseOperationError, OSError) as exc:
                raise _database_unavailable(exc) from exc
            if duplicate_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An active token already exists for this visitor and counter",
                )

        try:
            token = db.generate_token(request.counter_id, request.visitor_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Counter is unavailable",
            ) from exc
        except (db.DatabaseOperationError, OSError) as exc:
            raise _database_unavailable(exc) from exc

        try:
            queue_position = db.get_queue_position_by_tracking_reference(
                str(token["tracking_reference"])
            )
        except (db.DatabaseOperationError, OSError) as exc:
            logger.warning(
                "Could not retrieve queue position immediately after token issuance: %s",
                exc,
            )
            queue_position = None

        response = TokenIssueResponse(
            token_number=str(token["token_number"]),
            tracking_reference=str(token["tracking_reference"]),
            status="Waiting",
            queue_position=queue_position,
        )
        _remember_token_issue(idempotency_key, fingerprint, response)
        return response


@router.get(
    "/tokens/track/{tracking_reference}",
    response_model=TrackedTokenResponse,
)
def track_token(tracking_reference: str) -> TrackedTokenResponse:
    """Look up a token using its opaque reference, never an internal token ID."""
    if not _TRACKING_REFERENCE_PATTERN.fullmatch(tracking_reference):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )
    try:
        token = db.get_token_by_tracking_reference(tracking_reference)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )
        counter = db.get_counter_by_id(int(token["counter_id"]))
        if counter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )
        queue_position = db.get_queue_position_by_tracking_reference(
            tracking_reference
        )
    except HTTPException:
        raise
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc

    return TrackedTokenResponse(
        token_number=str(token["token_number"]),
        service_type=str(counter["service_type"]),
        counter_name=str(counter["counter_name"]),
        status=token["status"],
        created_at=str(token["created_at"]),
        queue_position=queue_position,
    )
