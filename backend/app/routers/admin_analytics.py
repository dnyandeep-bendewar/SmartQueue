"""Authenticated administrator analytics endpoints."""

from __future__ import annotations

import logging
import math
from datetime import datetime
from numbers import Real
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.routers.admin_auth import require_admin_session
from backend.app.security import AdminSession
from database import db
from models.predict import predict_waiting_time


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/analytics", tags=["admin analytics"])
ServiceStatus = Literal["Waiting", "Serving", "Served"]


class OverviewResponse(BaseModel):
    waiting_tokens: int
    serving_tokens: int
    currently_served_tokens: int
    historically_served_visitors: int
    active_counters: int
    total_counters: int


class DailyTrend(BaseModel):
    served_date: str
    visitor_count: int


class DailyTrendsResponse(BaseModel):
    trends: list[DailyTrend]


class ServiceBreakdownItem(BaseModel):
    service_type: str
    status: ServiceStatus
    token_count: int


class ServiceBreakdownResponse(BaseModel):
    breakdown: list[ServiceBreakdownItem]


class WaitingTimeObservation(BaseModel):
    recorded_at: str
    actual_waiting_time: float
    predicted_waiting_time: float


class WaitingTimesResponse(BaseModel):
    observations: list[WaitingTimeObservation]
    valid_observation_count: int
    sufficient_observations: bool
    excluded_observation_count: int


class CounterEstimate(BaseModel):
    counter_id: int
    counter_name: str
    service_type: str
    predicted_wait_minutes: float | None
    available: bool
    error_code: Literal["prediction_unavailable"] | None = None


class CounterEstimatesResponse(BaseModel):
    counters: list[CounterEstimate]
    recommended_counter_id: int | None


def _database_unavailable(exc: Exception) -> HTTPException:
    logger.warning("SmartQueue admin analytics database operation failed: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Analytics are temporarily unavailable",
    )


def _validated_prediction_inputs(counter: dict[str, object]) -> tuple[int, int, int]:
    values: dict[str, object] = {
        "people_waiting": counter["people_waiting"],
        "active_counters": counter["active_counters"],
        "avg_service_time": counter["avg_service_time"],
    }
    integers: dict[str, int] = {}
    ranges = {
        "people_waiting": (0, 50),
        "active_counters": (1, 5),
        "avg_service_time": (1, 15),
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or not float(value).is_integer()
        ):
            raise ValueError(f"{name} must be a whole number.")
        integer = int(value)
        minimum, maximum = ranges[name]
        if not minimum <= integer <= maximum:
            raise ValueError(f"{name} is outside the supported prediction range.")
        integers[name] = integer
    return (
        integers["people_waiting"],
        integers["active_counters"],
        integers["avg_service_time"],
    )


def _predict_counter(counter: dict[str, object], now: datetime) -> float:
    people_waiting, active_counters, avg_service_time = (
        _validated_prediction_inputs(counter)
    )
    estimate = predict_waiting_time(
        people_waiting=people_waiting,
        active_counters=active_counters,
        avg_service_time=avg_service_time,
        hour=min(max(now.hour, 9), 18),
        day_of_week=now.weekday(),
        service_type=str(counter["service_type"]),
    )
    if not math.isfinite(estimate) or estimate < 0:
        raise ValueError("Prediction is not a finite non-negative value.")
    return estimate


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> OverviewResponse:
    """Return current queue totals and historical served-token totals."""
    try:
        statistics = db.get_queue_statistics()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return OverviewResponse(
        waiting_tokens=int(statistics["waiting_tokens"]),
        serving_tokens=int(statistics["serving_tokens"]),
        currently_served_tokens=int(statistics["served_tokens"]),
        historically_served_visitors=int(statistics["historically_served_tokens"]),
        active_counters=int(statistics["active_counters"]),
        total_counters=int(statistics["total_counters"]),
    )


@router.get("/daily-trends", response_model=DailyTrendsResponse)
def get_daily_trends(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> DailyTrendsResponse:
    """Return chronological historical served counts from the existing query."""
    try:
        rows = db.get_daily_visitor_statistics()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return DailyTrendsResponse(
        trends=[
            DailyTrend(
                served_date=str(row["served_date"]),
                visitor_count=int(row["visitor_count"]),
            )
            for row in rows
        ]
    )


@router.get("/service-breakdown", response_model=ServiceBreakdownResponse)
def get_service_breakdown(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> ServiceBreakdownResponse:
    """Return token counts grouped by service and current supported status."""
    try:
        rows = db.get_service_token_statistics()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc
    return ServiceBreakdownResponse(
        breakdown=[
            ServiceBreakdownItem(
                service_type=str(row["service_type"]),
                status=row["status"],
                token_count=int(row["token_count"]),
            )
            for row in rows
        ]
    )


@router.get("/waiting-times", response_model=WaitingTimesResponse)
def get_waiting_times(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> WaitingTimesResponse:
    """Return valid recorded actual/predicted pairs without inventing history."""
    try:
        history = db.get_queue_history()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc

    observations: list[WaitingTimeObservation] = []
    for row in history:
        try:
            recorded_at = datetime.fromisoformat(
                str(row["recorded_at"]).replace("Z", "+00:00")
            )
            actual = row["actual_waiting_time"]
            predicted = row["predicted_waiting_time"]
            if (
                isinstance(actual, bool)
                or isinstance(predicted, bool)
                or not isinstance(actual, Real)
                or not isinstance(predicted, Real)
                or not math.isfinite(float(actual))
                or not math.isfinite(float(predicted))
                or float(actual) < 0
                or float(predicted) < 0
            ):
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        observations.append(
            WaitingTimeObservation(
                recorded_at=recorded_at.isoformat(),
                actual_waiting_time=float(actual),
                predicted_waiting_time=float(predicted),
            )
        )

    return WaitingTimesResponse(
        observations=observations,
        valid_observation_count=len(observations),
        sufficient_observations=len(observations) >= 2,
        excluded_observation_count=len(history) - len(observations),
    )


@router.get("/counter-estimates", response_model=CounterEstimatesResponse)
def get_counter_estimates(
    _: Annotated[AdminSession, Depends(require_admin_session)],
) -> CounterEstimatesResponse:
    """Estimate each active counter independently and recommend only if all succeed."""
    try:
        counters = db.get_all_counters()
    except (db.DatabaseOperationError, OSError) as exc:
        raise _database_unavailable(exc) from exc

    active_counters = [counter for counter in counters if bool(counter["is_active"])]
    now = datetime.now().astimezone()
    estimates: list[CounterEstimate] = []
    valid_predictions: dict[int, float] = {}
    for counter in active_counters:
        counter_id = int(counter["counter_id"])
        try:
            predicted_wait = _predict_counter(counter, now)
        except Exception as exc:
            logger.warning(
                "Waiting-time estimate unavailable for counter %s (%s)",
                counter_id,
                type(exc).__name__,
            )
            estimates.append(
                CounterEstimate(
                    counter_id=counter_id,
                    counter_name=str(counter["counter_name"]),
                    service_type=str(counter["service_type"]),
                    predicted_wait_minutes=None,
                    available=False,
                    error_code="prediction_unavailable",
                )
            )
            continue

        valid_predictions[counter_id] = predicted_wait
        estimates.append(
            CounterEstimate(
                counter_id=counter_id,
                counter_name=str(counter["counter_name"]),
                service_type=str(counter["service_type"]),
                predicted_wait_minutes=predicted_wait,
                available=True,
            )
        )

    recommended_counter_id = None
    if active_counters and len(valid_predictions) == len(active_counters):
        recommended_counter_id = min(
            valid_predictions,
            key=valid_predictions.__getitem__,
        )
    return CounterEstimatesResponse(
        counters=estimates,
        recommended_counter_id=recommended_counter_id,
    )
