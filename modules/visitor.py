"""Streamlit visitor portal for SmartQueue."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

import streamlit as st

from database import db
from models.predict import predict_waiting_time


SERVICE_TYPES = ["Certificate", "Fee Payment", "General Enquiry", "Admission"]
VISITOR_TOKENS_KEY = "visitor_issued_tokens"
TRACKED_REFERENCE_KEY = "visitor_tracked_token_reference"
LEGACY_TRACKED_TOKEN_KEY = "visitor_tracked_token_id"


def _predict_counter(counter: dict[str, Any], now: datetime) -> float:
    """Predict a wait from a counter row using the model's supported feature ranges."""
    people_waiting = int(counter["people_waiting"])
    active_counters = int(counter["active_counters"])
    avg_service_time = float(counter["avg_service_time"])

    if not 0 <= people_waiting <= 50:
        raise ValueError(
            f"Counter has {people_waiting} people waiting; the model supports 0–50."
        )
    if not 1 <= active_counters <= 5:
        raise ValueError(
            f"Counter has {active_counters} active positions; the model supports 1–5."
        )
    if not 1 <= avg_service_time <= 15 or not avg_service_time.is_integer():
        raise ValueError(
            f"Average service time is {avg_service_time:g} minutes; "
            "the model requires whole minutes from 1 to 15."
        )

    # The trained model only includes office hours; use the nearest supported hour.
    prediction_hour = min(max(now.hour, 9), 18)
    return predict_waiting_time(
        people_waiting=people_waiting,
        active_counters=active_counters,
        avg_service_time=int(avg_service_time),
        hour=prediction_hour,
        day_of_week=now.weekday(),
        service_type=str(counter["service_type"]),
    )


def _select_service(service_type: str) -> None:
    """Remember the service selected from the service-card controls."""
    st.session_state["visitor_selected_service"] = service_type


def _load_active_counters() -> list[dict[str, Any]] | None:
    """Retrieve active counters from the database, reporting persistence errors."""
    try:
        return [
            counter
            for counter in db.get_all_counters()
            if bool(counter.get("is_active"))
        ]
    except db.DatabaseOperationError:
        st.error("Service counters are temporarily unavailable. Please try again later.")
        return None


def _show_counter_cards(
    counters: list[dict[str, Any]],
    predictions: dict[int, float],
    recommended_counter_id: int | None,
) -> None:
    """Display matching active counters and highlight the fastest prediction."""
    if not counters:
        st.info("There are no active counters for this service right now.")
        return

    columns_per_row = 3
    for row_start in range(0, len(counters), columns_per_row):
        columns = st.columns(columns_per_row)
        for column, counter in zip(
            columns,
            counters[row_start : row_start + columns_per_row],
        ):
            counter_id = int(counter["counter_id"])
            is_recommended = counter_id == recommended_counter_id
            with column:
                with st.container(border=True):
                    if is_recommended:
                        st.success("Recommended · shortest predicted wait")
                    st.subheader(str(counter["counter_name"]))
                    detail_columns = st.columns(2)
                    detail_columns[0].caption(str(counter["service_type"]))
                    detail_columns[1].caption("Available")
                    st.metric("People waiting", int(counter.get("people_waiting") or 0))
                    if counter_id in predictions:
                        st.metric("Predicted wait", f"{predictions[counter_id]:.2f} min")
                    else:
                        st.warning("Prediction unavailable. You can still request a token.")


def _generate_token(
    counter: dict[str, Any],
    visitor_name: str,
    predicted_waiting_time: float | None,
) -> None:
    """Generate a token unless this session already has an active one for the counter."""
    counter_id = int(counter["counter_id"])
    issued_tokens = [
        {"tracking_reference": str(issued["tracking_reference"])}
        for issued in st.session_state.get(VISITOR_TOKENS_KEY, [])
        if isinstance(issued, dict)
        and isinstance(issued.get("tracking_reference"), str)
    ]

    # Keep reruns or repeated clicks from creating another active token in this session.
    for issued in issued_tokens:
        try:
            existing = db.get_token_by_tracking_reference(
                issued["tracking_reference"]
            )
        except db.DatabaseOperationError:
            st.error("We could not check your existing token. Please try again.")
            return
        if (
            existing is not None
            and int(existing["counter_id"]) == counter_id
            and existing["status"] in {"Waiting", "Serving"}
        ):
            st.session_state[TRACKED_REFERENCE_KEY] = issued["tracking_reference"]
            st.session_state[VISITOR_TOKENS_KEY] = issued_tokens
            st.info("You already have an active token for this counter. Its status is shown below.")
            return

    # If a name was supplied, also check active tokens at the selected counter.
    if visitor_name:
        try:
            duplicate_exists = db.has_active_token_for_visitor(
                counter_id,
                visitor_name,
            )
        except db.DatabaseOperationError:
            st.error("We could not check for an existing token. Please try again.")
            return
        if duplicate_exists:
            st.session_state[VISITOR_TOKENS_KEY] = issued_tokens
            st.info(
                "An active token for that name already exists at this counter. "
                "Use the secure tracking reference from that token to check its status."
            )
            return

    try:
        token = db.generate_token(counter_id, visitor_name or None)
    except (ValueError, db.DatabaseOperationError):
        st.error("We could not generate your token. Please try again or choose another counter.")
        return

    issued_tokens.append(
        {
            "tracking_reference": str(token["tracking_reference"]),
        }
    )
    st.session_state[VISITOR_TOKENS_KEY] = issued_tokens
    tracking_reference = str(token["tracking_reference"])
    st.session_state[TRACKED_REFERENCE_KEY] = tracking_reference

    try:
        queue_position = db.get_queue_position_by_tracking_reference(
            tracking_reference
        )
    except db.DatabaseOperationError:
        st.error("Your token was created, but its queue position is temporarily unavailable.")
        queue_position = None

    st.success("Your queue token is ready.")
    with st.container(border=True):
        st.markdown('<p class="sq-visitor-eyebrow">DIGITAL QUEUE TICKET</p>', unsafe_allow_html=True)
        st.markdown(f"# {token['token_number']}")
        st.caption(f"{counter['service_type']} · {counter['counter_name']}")
        detail_columns = st.columns(4)
        detail_columns[0].metric("Status", "Waiting")
        detail_columns[1].metric(
            "Queue position",
            f"{queue_position} ahead" if queue_position is not None else "Unavailable",
        )
        detail_columns[2].metric(
            "Estimated wait",
            f"{predicted_waiting_time:.2f} min"
            if predicted_waiting_time is not None
            else "Unavailable",
        )
        detail_columns[3].metric("Assigned counter", str(counter["counter_name"]))
    if predicted_waiting_time is None:
        st.warning(
            "A waiting-time estimate is unavailable for this counter. "
            "Your token was still created successfully."
        )
    st.warning(
        "Save your secure tracking reference. You will need it to check or refresh your token status."
    )
    st.code(tracking_reference, language=None)


def _find_token(reference: str) -> dict[str, Any] | None:
    """Retrieve a token only by its opaque tracking reference."""
    tracking_reference = reference.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", tracking_reference):
        return None

    try:
        return db.get_token_by_tracking_reference(tracking_reference)
    except db.DatabaseOperationError:
        st.error("We could not retrieve that token right now. Please try again.")
        return None


def _render_token_tracking() -> None:
    """Show refreshed token status, queue position, and its counter."""
    st.subheader("Track your token")
    st.caption("Enter the secure reference provided with your digital ticket. Refresh this page to update its status.")
    with st.form("visitor_token_tracking_form"):
        tracking_reference = st.text_input("Secure tracking reference", type="password")
        submitted = st.form_submit_button("Find my token", type="primary")
    if submitted:
        token = _find_token(tracking_reference)
        if token is None:
            st.error(
                "We couldn't find a token with that secure reference. Check that you "
                "entered the complete reference from your ticket."
            )
            st.session_state.pop(TRACKED_REFERENCE_KEY, None)
        else:
            st.session_state[TRACKED_REFERENCE_KEY] = str(
                token["tracking_reference"]
            )

    tracked_reference = st.session_state.get(TRACKED_REFERENCE_KEY)
    if not tracked_reference:
        return
    try:
        token = db.get_token_by_tracking_reference(str(tracked_reference))
    except db.DatabaseOperationError:
        st.error("We could not refresh your token status. Please try again.")
        return
    if token is None:
        st.warning("This token no longer exists.")
        st.session_state.pop(TRACKED_REFERENCE_KEY, None)
        return

    try:
        counter = db.get_counter_by_id(int(token["counter_id"]))
    except db.DatabaseOperationError:
        st.error("Your token was found, but its counter details are temporarily unavailable.")
        return

    if token["status"] == "Waiting":
        try:
            queue_position = db.get_queue_position_by_tracking_reference(
                str(token["tracking_reference"])
            )
        except db.DatabaseOperationError:
            st.error("Your token is waiting, but its queue position is temporarily unavailable.")
            queue_position = None
        position_text = (
            f"{queue_position} people ahead"
            if queue_position is not None
            else "Not waiting"
        )
    elif token["status"] == "Serving":
        position_text = "Now being served"
    else:
        position_text = "—"

    st.markdown("### Your token")
    with st.container(border=True):
        st.markdown('<p class="sq-visitor-eyebrow">LIVE TOKEN STATUS</p>', unsafe_allow_html=True)
        st.markdown(f"# {token['token_number']}")
        st.caption(f"{counter['service_type'] if counter is not None else 'Service'} · "
                   f"{counter['counter_name'] if counter is not None else 'Counter unavailable'}")
        if token["status"] == "Waiting":
            st.info("Your token is waiting in the queue.")
        elif token["status"] == "Serving":
            st.success("Now being served")
        else:
            st.success("Service complete. Your token has been served.")
        detail_columns = st.columns(3)
        detail_columns[0].metric("Status", str(token["status"]))
        detail_columns[1].metric("Queue position", position_text)
        detail_columns[2].metric(
            "Assigned counter",
            str(counter["counter_name"]) if counter is not None else "Unavailable",
        )


def render_visitor_portal() -> None:
    """Render the SmartQueue visitor service selection, token, and tracking portal."""
    # Discard any old session value that contained an internal sequential ID.
    st.session_state.pop(LEGACY_TRACKED_TOKEN_KEY, None)
    # Keep only opaque references if this session predates the secure tracking flow.
    st.session_state[VISITOR_TOKENS_KEY] = [
        {"tracking_reference": issued["tracking_reference"]}
        for issued in st.session_state.get(VISITOR_TOKENS_KEY, [])
        if isinstance(issued, dict)
        and isinstance(issued.get("tracking_reference"), str)
    ]
    st.markdown('<p class="sq-visitor-eyebrow">VISITOR SERVICES</p>', unsafe_allow_html=True)
    st.title("Welcome to SmartQueue")
    st.write(
        "Manage your visit with a digital queue token. Choose a service to compare "
        "active counters, get a wait estimate and track your status."
    )
    st.caption(
        "Select a service, choose a counter and request your token. Keep the secure "
        "tracking reference to check your queue status later."
    )
    st.info(
        "For tokens issued before secure tracking was enabled, contact an administrator "
        "to receive a reference securely or request a replacement token."
    )

    try:
        all_counters = db.get_all_counters()
    except db.DatabaseOperationError:
        st.error("Available counters are temporarily unavailable. Please try again later.")
        return

    active_counters = [
        counter for counter in all_counters if bool(counter.get("is_active"))
    ]

    st.subheader("1. Choose a service")
    if "visitor_selected_service" not in st.session_state:
        st.session_state["visitor_selected_service"] = SERVICE_TYPES[0]
    service_columns = st.columns(4, gap="small")
    for column, service_type in zip(service_columns, SERVICE_TYPES):
        column.button(
            service_type,
            key=f"visitor_service_{service_type.lower().replace(' ', '_')}",
            type=(
                "primary"
                if st.session_state["visitor_selected_service"] == service_type
                else "secondary"
            ),
            on_click=_select_service,
            args=(service_type,),
            width="stretch",
        )
    selected_service = st.session_state["visitor_selected_service"]
    matching_counters = [
        counter
        for counter in active_counters
        if counter.get("service_type") == selected_service
    ]

    now = datetime.now().astimezone()
    if now.hour < 9 or now.hour > 18:
        prediction_hour = min(max(now.hour, 9), 18)
        st.info(
            f"Predictions use the nearest model-supported office hour "
            f"({prediction_hour:02d}:00); the model was trained for 09:00–18:00."
        )

    predictions: dict[int, float] = {}
    prediction_errors: dict[int, str] = {}
    for counter in matching_counters:
        counter_id = int(counter["counter_id"])
        try:
            predictions[counter_id] = _predict_counter(counter, now)
        except (ValueError, FileNotFoundError, OSError, EOFError, ImportError) as exc:
            prediction_errors[counter_id] = str(exc)
        except Exception as exc:
            prediction_errors[counter_id] = (
                f"Unexpected prediction error ({type(exc).__name__}): {exc}"
            )

    recommended_counter_id = (
        min(predictions, key=predictions.__getitem__)
        if predictions and len(predictions) == len(matching_counters)
        else None
    )

    st.subheader(f"2. Counters for {selected_service}")
    _show_counter_cards(matching_counters, predictions, recommended_counter_id)
    for counter in matching_counters:
        error = prediction_errors.get(int(counter["counter_id"]))
        if error:
            st.warning(
                f"{counter['counter_name']}: prediction unavailable. "
                "You can still request a token."
            )
    if len(predictions) > 1 and recommended_counter_id is not None:
        recommended = next(
            counter
            for counter in matching_counters
            if int(counter["counter_id"]) == recommended_counter_id
        )
        st.success(
            f"Recommended: {recommended['counter_name']} — "
            f"{predictions[recommended_counter_id]:.2f} minutes predicted."
        )
    elif len(predictions) == 1 and recommended_counter_id is not None:
        st.success(
            "This is the only matching active counter: "
            f"{predictions[recommended_counter_id]:.2f} minutes predicted."
        )
    elif matching_counters:
        st.info(
            "A recommendation is unavailable until every matching active counter "
            "has a valid prediction."
        )

    st.subheader("3. Get your digital token")
    if not matching_counters:
        if active_counters:
            st.info("No active counters currently serve this service.")
        else:
            st.info("There are no active service counters at the moment.")
    else:
        counter_by_label = {
            (
                f"{counter['counter_name']} — {counter['service_type']} "
                f"(ID {counter['counter_id']})"
            ): counter
            for counter in matching_counters
        }
        labels = list(counter_by_label)
        recommended_label = next(
            (
                label
                for label, counter in counter_by_label.items()
                if int(counter["counter_id"]) == recommended_counter_id
            ),
            labels[0],
        )
        with st.form("visitor_generate_token_form"):
            visitor_name = st.text_input("Your name (optional)", max_chars=100)
            selected_label = st.selectbox(
                "Choose a counter",
                labels,
                index=labels.index(recommended_label),
            )
            submitted = st.form_submit_button("Get my token", type="primary")
        if submitted:
            _generate_token(
                counter_by_label[selected_label],
                visitor_name.strip(),
                predictions.get(int(counter_by_label[selected_label]["counter_id"])),
            )

    st.divider()
    st.subheader("4. Track your queue status")
    _render_token_tracking()