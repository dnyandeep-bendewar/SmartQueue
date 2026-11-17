"""Streamlit analytics dashboard for SmartQueue."""

from __future__ import annotations

import math
from datetime import datetime
from numbers import Real
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from database import db
from models.predict import predict_waiting_time
from utils.helpers import get_current_theme, get_plotly_theme


def _predict_counter_wait(counter: dict[str, Any], now: datetime) -> float:
    """Predict an active counter's current wait using its stored queue inputs."""
    people_waiting = counter["people_waiting"]
    active_counters = counter["active_counters"]
    avg_service_time = counter["avg_service_time"]

    integer_inputs = {
        "people_waiting": people_waiting,
        "active_counters": active_counters,
        "avg_service_time": avg_service_time,
    }
    for name, value in integer_inputs.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or not float(value).is_integer()
        ):
            raise ValueError(f"{name} must be a whole number; received {value!r}.")

    people_waiting = int(people_waiting)
    active_counters = int(active_counters)
    avg_service_time = int(avg_service_time)
    if not 0 <= people_waiting <= 50:
        raise ValueError("people_waiting must be between 0 and 50 for this model.")
    if not 1 <= active_counters <= 5:
        raise ValueError("active_counters must be between 1 and 5 for this model.")
    if not 1 <= avg_service_time <= 15:
        raise ValueError("avg_service_time must be between 1 and 15 for this model.")

    return predict_waiting_time(
        people_waiting=people_waiting,
        active_counters=active_counters,
        avg_service_time=avg_service_time,
        hour=min(max(now.hour, 9), 18),
        day_of_week=now.weekday(),
        service_type=str(counter["service_type"]),
    )


def _render_counter_predictions(
    counters: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Render current model estimates and return successful predictions."""
    st.subheader("Counter waiting-time estimates")
    st.caption(
        "Current model predictions for active counters. These estimates are not "
        "measured actual waiting times."
    )
    active_counters = [counter for counter in counters if counter.get("is_active")]
    if not active_counters:
        st.info("No active counters are available for waiting-time predictions.")
        return []

    if now.hour < 9 or now.hour > 18:
        prediction_hour = min(max(now.hour, 9), 18)
        st.info(
            "The model was trained for hours 09:00–18:00. Estimates use the nearest "
            f"supported hour, {prediction_hour:02d}:00."
        )

    prediction_rows: list[dict[str, Any]] = []
    for counter in active_counters:
        row: dict[str, Any] = {
            "Counter": str(counter["counter_name"]),
            "Service type": str(counter["service_type"]),
            "People waiting": counter.get("people_waiting"),
            "Predicted wait (minutes)": None,
        }
        try:
            row["Predicted wait (minutes)"] = _predict_counter_wait(counter, now)
        except (ValueError, FileNotFoundError, OSError, EOFError, ImportError) as exc:
            st.warning(
                f"Prediction unavailable for {row['Counter']}: {exc}"
            )
        except Exception as exc:
            st.warning(
                f"Prediction unavailable for {row['Counter']}: "
                f"Unexpected prediction error ({type(exc).__name__}): {exc}"
            )
        prediction_rows.append(row)

    available = [
        row for row in prediction_rows
        if row["Predicted wait (minutes)"] is not None
    ]
    if available:
        frame = pd.DataFrame(available)
        chart = px.bar(
            frame,
            x="Counter",
            y="Predicted wait (minutes)",
            color="Service type",
            color_discrete_sequence=get_plotly_theme()["colorway"],
            title="Predicted wait by active counter",
            labels={
                "Counter": "Service counter",
                "Predicted wait (minutes)": "Predicted wait (minutes)",
                "Service type": "Service",
            },
            hover_data=["People waiting"],
        )
        chart.update_layout(
            **get_plotly_theme(),
            yaxis_title="Predicted wait (minutes)",
            xaxis_title="Service counter",
            hovermode="closest",
            margin={"t": 70, "r": 24, "b": 50, "l": 60},
        )
        chart.update_traces(
            hovertemplate=(
                "<b>%{x}</b><br>Predicted wait: %{y:.2f} min"
                "<br>People waiting: %{customdata[0]}<extra></extra>"
            )
        )
        st.plotly_chart(chart, width="stretch")
        cards = st.columns(3, gap="medium")
        for index, row in enumerate(available):
            with cards[index % len(cards)]:
                with st.container(border=True):
                    st.caption(str(row["Service type"]))
                    st.markdown(f"### {row['Counter']}")
                    st.metric(
                        "Predicted wait",
                        f"{float(row['Predicted wait (minutes)']):.2f} min",
                    )
                    st.caption(f"{row['People waiting']} people currently waiting")
    else:
        st.info("No active counter currently has a valid model prediction.")
    return available


def _render_service_distribution(
    counters: list[dict[str, Any]],
    statistics: dict[str, Any],
    counters_available: bool,
) -> None:
    """Show the service mix of waiting tokens, the available service-level count."""
    st.subheader("Current waiting visitors by service type")
    if not counters_available:
        st.info("The service breakdown is unavailable because counters could not be loaded.")
        return

    waiting_by_counter = {
        int(row["counter_id"]): int(row["waiting_tokens"] or 0)
        for row in statistics["counters"]
    }
    counts_by_service: dict[str, int] = {}
    for counter in counters:
        service_type = str(counter["service_type"])
        count = waiting_by_counter.get(int(counter["counter_id"]), 0)
        counts_by_service[service_type] = counts_by_service.get(service_type, 0) + count

    counts = [
        {"Service type": service_type, "Waiting visitors": count}
        for service_type, count in counts_by_service.items()
        if count > 0
    ]
    if not counts:
        st.info("There are no waiting tokens to break down by service type.")
        return

    chart = px.pie(
        pd.DataFrame(counts),
        names="Service type",
        values="Waiting visitors",
        title="Distribution of currently waiting tokens by service",
        hole=0.35,
        color_discrete_sequence=get_plotly_theme()["colorway"],
    )
    chart.update_layout(**get_plotly_theme(), legend_title_text="Service")
    st.plotly_chart(chart, width="stretch")
    st.caption(
        "This chart covers current Waiting tokens only; the database API does not "
        "provide a service-type breakdown for all historical token statuses."
    )


def _render_daily_trend(daily_statistics: list[dict[str, Any]]) -> None:
    st.subheader("Daily visitor trend")
    st.caption("Visitors counted by their recorded served date, regardless of current token status.")
    if not daily_statistics:
        st.info("No served-token records with a served timestamp are available yet.")
        return

    frame = pd.DataFrame(daily_statistics)
    if not {"served_date", "visitor_count"}.issubset(frame.columns):
        st.warning("Daily visitor statistics are missing required fields.")
        return

    frame["served_date"] = pd.to_datetime(frame["served_date"], errors="coerce")
    frame["visitor_count"] = pd.to_numeric(frame["visitor_count"], errors="coerce")
    frame = frame.dropna(subset=["served_date", "visitor_count"]).sort_values(
        "served_date"
    )
    if frame.empty:
        st.info("No valid daily served-token statistics are available.")
        return

    chart = px.line(
        frame,
        x="served_date",
        y="visitor_count",
        markers=True,
        title="Visitors served over time",
        labels={
            "served_date": "Date",
            "visitor_count": "Visitors served",
        },
    )
    chart.update_layout(
        **get_plotly_theme(),
        xaxis_title="Served date",
        yaxis_title="Visitor count",
        hovermode="x unified",
        margin={"t": 70, "r": 24, "b": 50, "l": 55},
    )
    chart.update_traces(
        line={"color": get_plotly_theme()["colorway"][0], "width": 3},
        marker={"size": 8},
        hovertemplate="%{x|%b %d, %Y}<br>Visitors served: %{y}<extra></extra>",
    )
    st.plotly_chart(chart, width="stretch")


def _render_service_token_status(
    service_statistics: list[dict[str, Any]],
) -> None:
    st.subheader("Service-wise token status")
    st.caption("Compare the current Waiting, Serving and Served token counts for each service.")
    if not service_statistics:
        st.info("No tokens are available for the service-wise status comparison.")
        return

    frame = pd.DataFrame(service_statistics)
    required_columns = {"service_type", "status", "token_count"}
    if not required_columns.issubset(frame.columns):
        st.warning("Service token statistics are missing required fields.")
        return

    frame["token_count"] = pd.to_numeric(frame["token_count"], errors="coerce")
    frame = frame.dropna(subset=["service_type", "status", "token_count"])
    if frame.empty:
        st.info("No valid service-wise token status counts are available.")
        return

    status_order = ["Waiting", "Serving", "Served"]
    frame["status"] = pd.Categorical(
        frame["status"],
        categories=status_order,
        ordered=True,
    )
    frame = frame.dropna(subset=["status"])
    if frame.empty:
        st.info("No tokens with a supported queue status are available.")
        return

    chart = px.bar(
        frame,
        x="service_type",
        y="token_count",
        color="status",
        barmode="group",
        category_orders={"status": status_order},
        color_discrete_map=(
            {
                "Waiting": "#0D9488",
                "Serving": "#3B82F6",
                "Served": "#94A3B8",
            }
            if get_current_theme() == "Light"
            else {
                "Waiting": "#2DD4BF",
                "Serving": "#60A5FA",
                "Served": "#CBD5E1",
            }
        ),
        title="Current token status by service",
        labels={
            "service_type": "Service type",
            "token_count": "Token count",
            "status": "Token status",
        },
    )
    plotly_theme = get_plotly_theme()
    chart.update_layout(
        **plotly_theme,
        xaxis_title="Service type",
        yaxis_title="Token count",
        legend_title_text="Current status",
        bargap=0.25,
        margin={"t": 70, "r": 24, "b": 50, "l": 55},
    )
    chart.update_traces(
        hovertemplate="%{x}<br>%{fullData.name}: %{y} tokens<extra></extra>"
    )
    st.plotly_chart(chart, width="stretch")


def _render_waiting_history(history: list[dict[str, Any]]) -> None:
    st.subheader("Actual vs. predicted waiting time")
    st.caption(
        "Recorded queue-history observations only. Actual and model-predicted values "
        "remain separate series."
    )
    if len(history) < 2:
        st.info(
            "At least two recorded queue-history observations are needed for a "
            "historical comparison chart."
        )
        return

    frame = pd.DataFrame(history)
    required_columns = {
        "recorded_at",
        "actual_waiting_time",
        "predicted_waiting_time",
    }
    if not required_columns.issubset(frame.columns):
        st.warning("Queue history is missing fields required for the comparison.")
        return

    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], errors="coerce")
    for column in ("actual_waiting_time", "predicted_waiting_time"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    valid = frame.dropna(
        subset=["recorded_at", "actual_waiting_time", "predicted_waiting_time"]
    ).copy()
    finite_rows = valid[
        valid["actual_waiting_time"].map(math.isfinite)
        & valid["predicted_waiting_time"].map(math.isfinite)
    ].sort_values("recorded_at")
    if len(finite_rows) < 2:
        st.info(
            "Fewer than two valid observations contain both actual and predicted "
            "waiting times."
        )
        if len(valid) != len(frame):
            st.warning("Some malformed or incomplete history records were excluded.")
        return

    chart_data = finite_rows.melt(
        id_vars="recorded_at",
        value_vars=["actual_waiting_time", "predicted_waiting_time"],
        var_name="Measure",
        value_name="Waiting time (minutes)",
    )
    chart_data["Measure"] = chart_data["Measure"].map(
        {
            "actual_waiting_time": "Actual",
            "predicted_waiting_time": "Predicted",
        }
    )
    chart = px.line(
        chart_data,
        x="recorded_at",
        y="Waiting time (minutes)",
        color="Measure",
        color_discrete_map=(
            {"Actual": "#0D9488", "Predicted": "#3B82F6"}
            if get_current_theme() == "Light"
            else {"Actual": "#2DD4BF", "Predicted": "#60A5FA"}
        ),
        markers=True,
        title="Recorded waiting-time comparison",
        labels={"recorded_at": "Observation time"},
    )
    chart.update_layout(
        **get_plotly_theme(),
        xaxis_title="Observation time",
        yaxis_title="Waiting time (minutes)",
        legend_title_text="Measure",
        hovermode="x unified",
        margin={"t": 70, "r": 24, "b": 50, "l": 60},
    )
    chart.update_traces(
        line={"width": 2.5},
        marker={"size": 8},
        hovertemplate="%{x|%b %d, %Y %H:%M}<br>%{fullData.name}: %{y:.2f} min<extra></extra>",
    )
    st.plotly_chart(chart, width="stretch")
    if len(valid) != len(frame):
        st.warning("Some malformed or incomplete history records were excluded.")


def render_analytics_dashboard() -> None:
    """Render analytics based only on counters, tokens, predictions, and stored history."""
    st.markdown('<p class="sq-analytics-eyebrow">QUEUE INTELLIGENCE</p>', unsafe_allow_html=True)
    st.title("Analytics dashboard")
    st.caption(
        "Understand live queue activity, service trends and model estimates using "
        "recorded SmartQueue data."
    )

    try:
        statistics = db.get_queue_statistics()
    except db.DatabaseOperationError:
        st.error("Queue statistics are temporarily unavailable. Please try again later.")
        return

    try:
        counters = db.get_all_counters()
    except db.DatabaseOperationError:
        st.error(
            "Service counters are temporarily unavailable. Counter estimates and "
            "service breakdown cannot be shown."
        )
        counters = []
        counters_available = False
    else:
        counters_available = True

    try:
        history = db.get_queue_history()
    except db.DatabaseOperationError:
        st.error("Recorded waiting-time history is temporarily unavailable.")
        history = []

    metrics = st.columns(4, gap="medium")
    metrics[0].metric(
        "Visitors ever served",
        int(statistics["historically_served_tokens"]),
        help="Tokens with a recorded served_at timestamp, regardless of current queue status.",
    )
    metrics[1].metric(
        "Currently waiting",
        int(statistics["waiting_tokens"]),
        help="Count of tokens currently in Waiting status.",
    )
    metrics[2].metric(
        "Currently serving",
        int(statistics["serving_tokens"]),
        help="Count of tokens currently in Serving status.",
    )
    metrics[3].metric("Active counters", int(statistics["active_counters"]))

    if counters_available:
        now = datetime.now().astimezone()
        prediction_rows = _render_counter_predictions(counters, now)
    else:
        st.subheader("Counter waiting-time estimates")
        prediction_rows = []
    average_prediction: str | float = (
        round(
            sum(float(row["Predicted wait (minutes)"]) for row in prediction_rows)
            / len(prediction_rows),
            2,
        )
        if prediction_rows
        else "N/A"
    )
    st.metric(
        "Average predicted wait (min)",
        average_prediction,
        help="Average of available predictions for active counters; not actual wait.",
    )

    if counters_available and not counters:
        st.info("No service counters have been configured yet.")
    _render_service_distribution(counters, statistics, counters_available)
    try:
        daily_statistics = db.get_daily_visitor_statistics()
    except db.DatabaseOperationError:
        st.error("Daily visitor statistics are temporarily unavailable.")
    else:
        _render_daily_trend(daily_statistics)

    try:
        service_statistics = db.get_service_token_statistics()
    except db.DatabaseOperationError:
        st.error("Service-wise token statistics are temporarily unavailable.")
    else:
        _render_service_token_status(service_statistics)

    _render_waiting_history(history)