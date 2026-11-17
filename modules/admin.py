"""Streamlit admin dashboard for SmartQueue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from database import db
from models.predict import predict_waiting_time


SERVICE_TYPES = ["Certificate", "Fee Payment", "General Enquiry", "Admission"]


def _show_login() -> bool:
    """Render the login form and return whether the current session is authenticated."""
    if st.session_state.get("admin_authenticated", False):
        return True

    st.title("SmartQueue Admin")
    st.caption("Sign in to manage service counters and queues.")
    with st.form("admin_login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in", type="primary", width="stretch")

    if submitted:
        try:
            authenticated = db.authenticate_admin(username.strip(), password)
        except db.DatabaseOperationError as exc:
            st.error(f"Could not authenticate against the database: {exc}")
        else:
            if authenticated:
                st.session_state["admin_authenticated"] = True
                st.session_state["admin_username"] = username.strip()
                st.rerun()
            else:
                st.error("The username or password is incorrect.")
    return False


def _load_counters() -> list[dict[str, Any]] | None:
    """Load counters, reporting database errors in the dashboard."""
    try:
        return db.get_all_counters()
    except db.DatabaseOperationError as exc:
        st.error(f"Could not load service counters: {exc}")
        return None


def _predict_counter_wait(counter: dict[str, Any], now: datetime) -> float:
    """Predict from stored counter values without silently coercing invalid data."""
    people_waiting = int(counter["people_waiting"])
    active_count = int(counter["active_counters"])
    service_time = float(counter["avg_service_time"])
    if people_waiting > 50:
        raise ValueError(
            f"people_waiting is {people_waiting}; the model was trained for values up to 50."
        )
    if not 1 <= active_count <= 5:
        raise ValueError(
            f"active_counters is {active_count}; the model supports values from 1 to 5."
        )
    if not 1 <= service_time <= 15:
        raise ValueError(
            f"avg_service_time is {service_time}; the model supports values from 1 to 15."
        )
    if not service_time.is_integer():
        raise ValueError(
            f"avg_service_time is {service_time}; the model expects whole-minute values."
        )
    # The model was trained only for office hours; use the nearest trained hour outside them.
    prediction_hour = min(max(now.hour, 9), 18)
    return predict_waiting_time(
        people_waiting=people_waiting,
        active_counters=active_count,
        avg_service_time=int(service_time),
        hour=prediction_hour,
        day_of_week=now.weekday(),
        service_type=str(counter["service_type"]),
    )


def _show_prediction_hour_notice(now: datetime) -> None:
    """Explain when the model uses its nearest supported hour."""
    if now.hour < 9 or now.hour > 18:
        prediction_hour = min(max(now.hour, 9), 18)
        st.info(
            f"The model was trained for hours 09:00–18:00. Since it is currently "
            f"{now:%H:%M}, estimates use the nearest supported hour "
            f"{prediction_hour:02d}:00."
        )


def _render_overview(counters: list[dict[str, Any]]) -> None:
    st.markdown('<p class="sq-admin-eyebrow">OPERATIONS</p>', unsafe_allow_html=True)
    st.title("Admin overview")
    st.caption("A live view of visitor activity, service counters and predicted queue times.")
    try:
        statistics = db.get_queue_statistics()
    except db.DatabaseOperationError as exc:
        st.error(f"Could not load queue statistics: {exc}")
        statistics = None
    waiting_visitors: int | str = (
        int(statistics["waiting_tokens"]) if statistics is not None else "N/A"
    )
    serving_visitors: int | str = (
        int(statistics["serving_tokens"]) if statistics is not None else "N/A"
    )
    historically_served = (
        int(statistics["historically_served_tokens"])
        if statistics is not None
        else "N/A"
    )
    active_counters: int | str = (
        int(statistics["active_counters"]) if statistics is not None else "N/A"
    )

    metric_columns = st.columns(4, gap="medium")
    metric_columns[0].metric("Currently waiting", waiting_visitors)
    metric_columns[1].metric("Currently serving", serving_visitors)
    metric_columns[2].metric(
        "Visitors ever served",
        historically_served,
        help="Tokens with a recorded served_at timestamp, regardless of current status.",
    )
    metric_columns[3].metric("Active service counters", active_counters)

    now = datetime.now().astimezone()
    _show_prediction_hour_notice(now)
    if counters:
        st.subheader("Service counters")
        counter_columns = st.columns(3, gap="medium")
        predicted_values: list[float] = []
        for index, counter in enumerate(counters):
            with counter_columns[index % len(counter_columns)]:
                estimate = _render_counter_card(counter, now)
                if estimate is not None:
                    predicted_values.append(estimate)
    else:
        st.info("No service counters have been added yet. Add a counter to start managing queues.")
        predicted_values = []

    average_prediction: str | float = (
        round(sum(predicted_values) / len(predicted_values), 2)
        if predicted_values
        else "N/A"
    )
    st.metric(
        "Average predicted wait (min)",
        average_prediction,
        help="Average of valid model estimates for active counters; not actual wait.",
    )


def _render_counter_card(
    counter: dict[str, Any],
    now: datetime,
) -> float | None:
    """Display key operational details and a valid estimate for one counter."""
    is_active = bool(counter.get("is_active"))
    with st.container(border=True):
        status_class = "sq-status-active" if is_active else "sq-status-inactive"
        status_text = "Active" if is_active else "Inactive"
        st.markdown(
            f'<span class="sq-status-badge {status_class}">{status_text}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"### {counter['counter_name']}")
        st.caption(f"{counter['service_type']} · Counter {counter['counter_id']}")
        detail_columns = st.columns(2)
        detail_columns[0].metric("People waiting", int(counter.get("people_waiting") or 0))
        detail_columns[1].metric(
            "Avg. service",
            f"{float(counter.get('avg_service_time') or 0):g} min",
        )
        if is_active:
            try:
                estimate = _predict_counter_wait(counter, now)
            except (ValueError, FileNotFoundError, OSError, EOFError, ImportError) as exc:
                st.warning(f"{counter['counter_name']}: prediction unavailable — {exc}")
                return None
            except Exception as exc:
                st.warning(
                    f"{counter['counter_name']}: prediction unavailable — "
                    f"Unexpected prediction error ({type(exc).__name__}): {exc}"
                )
                return None
            else:
                st.metric("Predicted wait", f"{estimate:.2f} min")
        else:
            st.caption("Activate this counter to include it in predictions.")
            return None
    return estimate


def _render_counter_management(counters: list[dict[str, Any]]) -> None:
    st.markdown('<p class="sq-admin-eyebrow">CONFIGURATION</p>', unsafe_allow_html=True)
    st.title("Service counter management")
    st.caption("Add service points and keep capacity, wait inputs and availability up to date.")

    with st.container(border=True):
        st.subheader("Add a service counter")
        with st.form("add_counter_form"):
            form_columns = st.columns(2, gap="medium")
            counter_name = form_columns[0].text_input("Counter name", max_chars=100)
            service_type = form_columns[1].selectbox("Service type", SERVICE_TYPES)
            active_count = form_columns[0].number_input(
                "Active service positions", min_value=1, max_value=5, value=1
            )
            average_service_time = form_columns[1].number_input(
                "Average service time (minutes)",
                min_value=1.0,
                max_value=15.0,
                value=5.0,
                step=1.0,
            )
            submitted = st.form_submit_button("Add counter", type="primary")
    if submitted:
        if not counter_name.strip():
            st.error("Enter a counter name.")
        else:
            try:
                counter_id = db.add_counter(
                    counter_name.strip(),
                    service_type,
                    int(active_count),
                    float(average_service_time),
                )
            except (ValueError, db.DatabaseOperationError) as exc:
                st.error(f"Could not add the counter: {exc}")
            else:
                st.success(f"Counter added (ID {counter_id}).")
                st.rerun()

    if not counters:
        st.info("No counters to edit yet.")
        return

    st.subheader("Edit an existing counter")
    counter_labels = {
        f"{counter['counter_name']} (ID {counter['counter_id']})": counter
        for counter in counters
    }
    selected_label = st.selectbox("Select a counter to edit", list(counter_labels))
    selected_counter = counter_labels[selected_label]
    stored_people_waiting = int(selected_counter["people_waiting"] or 0)
    stored_service_time = float(selected_counter["avg_service_time"] or 5)
    if not 0 <= stored_people_waiting <= 50:
        st.warning(
            f"This counter currently has {stored_people_waiting} people waiting. "
            "The prediction model supports 0–50; saving a value in that range will make "
            "predictions available."
        )
    if (
        not 1 <= stored_service_time <= 15
        or not stored_service_time.is_integer()
    ):
        st.warning(
            f"This counter's average service time is {stored_service_time:g} minutes. "
            "The prediction model supports whole-minute values from 1 to 15."
        )
    people_waiting_default = min(50, max(0, stored_people_waiting))
    service_time_default = min(15, max(1, round(stored_service_time)))
    with st.container(border=True):
        st.caption(
            f"{selected_counter['counter_name']} · {selected_counter['service_type']}"
        )
        with st.form(f"edit_counter_form_{selected_counter['counter_id']}"):
            form_columns = st.columns(2, gap="medium")
            form_columns[0].text_input(
                "Counter name", value=selected_counter["counter_name"], disabled=True
            )
            form_columns[1].selectbox(
                "Service type",
                SERVICE_TYPES,
                index=SERVICE_TYPES.index(selected_counter["service_type"])
                if selected_counter["service_type"] in SERVICE_TYPES
                else 0,
                disabled=True,
            )
            people_waiting = form_columns[0].number_input(
                "People waiting",
                min_value=0,
                max_value=50,
                value=people_waiting_default,
            )
            active_count = form_columns[1].number_input(
                "Active service positions",
                min_value=1,
                max_value=5,
                value=max(1, min(5, int(selected_counter["active_counters"] or 1))),
            )
            average_service_time = form_columns[0].number_input(
                "Average service time (minutes)",
                min_value=1,
                max_value=15,
                value=service_time_default,
                step=1,
            )
            is_active = form_columns[1].checkbox(
                "Counter is active", value=bool(selected_counter["is_active"])
            )
            submitted = st.form_submit_button("Save counter settings", type="primary")
    if submitted:
        try:
            updated = db.update_counter(
                int(selected_counter["counter_id"]),
                int(people_waiting),
                int(active_count),
                float(average_service_time),
                is_active,
            )
        except (ValueError, db.DatabaseOperationError) as exc:
            st.error(f"Could not update the counter: {exc}")
        else:
            if updated:
                st.success("Counter settings updated.")
                st.rerun()
            else:
                st.error("The counter no longer exists.")

    st.caption(
        "Counter name and service type are read-only because the current database API "
        "does not provide an update operation for those fields."
    )
    st.subheader("All counters")
    counter_columns = st.columns(3, gap="medium")
    for index, counter in enumerate(counters):
        with counter_columns[index % len(counter_columns)]:
            _render_counter_card(counter, datetime.now().astimezone())


def _render_queue_management(counters: list[dict[str, Any]]) -> None:
    st.markdown('<p class="sq-admin-eyebrow">VISITOR FLOW</p>', unsafe_allow_html=True)
    st.title("Queue management")
    st.caption("Review active tokens and advance each visitor through service.")
    if not counters:
        st.info("No service counters are available.")
        return

    for counter in counters:
        title = f"{counter['counter_name']} — {counter['service_type']}"
        with st.expander(title, expanded=True):
            try:
                tokens = db.get_active_queue_tokens(int(counter["counter_id"]))
            except db.DatabaseOperationError as exc:
                st.error(f"Could not load this queue: {exc}")
                continue
            if not tokens:
                st.caption("No active tokens in this queue.")
                continue

            for token in tokens:
                with st.container(border=True):
                    token_columns = st.columns([2, 1, 1], gap="medium")
                    token_columns[0].markdown(f"### {token['token_number']}")
                    token_columns[0].caption(
                        f"{counter['service_type']} · {counter['counter_name']}"
                    )
                    token_columns[0].caption(
                        f"Visitor: {token.get('visitor_name') or '—'} · "
                        f"Created: {token['created_at']}"
                    )
                    token_columns[1].markdown(
                        f'<span class="sq-status-badge sq-status-{token["status"].lower()}">'
                        f'{token["status"]}</span>',
                        unsafe_allow_html=True,
                    )
                    serve_label = "Start serving"
                    if token_columns[2].button(
                        serve_label,
                        key=f"serve_token_{token['token_id']}",
                        disabled=token["status"] != "Waiting",
                        type="primary" if token["status"] == "Waiting" else "secondary",
                        width="stretch",
                    ):
                        try:
                            updated = db.update_token_status(int(token["token_id"]), "Serving")
                        except (ValueError, db.DatabaseOperationError) as exc:
                            st.error(f"Could not update token status: {exc}")
                        else:
                            if updated:
                                st.success("Token is now being served.")
                                st.rerun()
                            else:
                                st.error("The token no longer exists.")
                    if token_columns[2].button(
                        "Mark served",
                        key=f"complete_token_{token['token_id']}",
                        disabled=token["status"] not in {"Waiting", "Serving"},
                        width="stretch",
                    ):
                        try:
                            updated = db.update_token_status(int(token["token_id"]), "Served")
                        except (ValueError, db.DatabaseOperationError) as exc:
                            st.error(f"Could not update token status: {exc}")
                        else:
                            if updated:
                                st.success("Token marked as served.")
                                st.rerun()
                            else:
                                st.error("The token no longer exists.")


def _render_predictions(counters: list[dict[str, Any]]) -> None:
    st.markdown('<p class="sq-admin-eyebrow">MODEL OUTPUTS</p>', unsafe_allow_html=True)
    st.title("Waiting time predictions")
    st.caption("Valid model estimates for active counters. Predictions are not measured actual waits.")
    active_counters = [counter for counter in counters if counter.get("is_active")]
    if not active_counters:
        st.info("No active counters are available for prediction.")
        return

    now = datetime.now().astimezone()
    _show_prediction_hour_notice(now)
    prediction_rows: list[dict[str, Any]] = []
    for counter in active_counters:
        try:
            estimate = _predict_counter_wait(counter, now)
        except (ValueError, FileNotFoundError, OSError, EOFError, ImportError) as exc:
            st.warning(f"{counter['counter_name']}: prediction unavailable — {exc}")
        except Exception as exc:
            st.warning(
                f"{counter['counter_name']}: prediction unavailable — "
                f"Unexpected prediction error ({type(exc).__name__}): {exc}"
            )
            continue
        prediction_rows.append(
            {
                "Counter": counter["counter_name"],
                "Service": counter["service_type"],
                "People waiting": counter["people_waiting"],
                "Predicted wait": estimate,
            }
        )
    if prediction_rows:
        prediction_columns = st.columns(3, gap="medium")
        for index, row in enumerate(prediction_rows):
            with prediction_columns[index % len(prediction_columns)]:
                with st.container(border=True):
                    st.caption(row["Service"])
                    st.markdown(f"### {row['Counter']}")
                    st.metric("Predicted wait", f"{row['Predicted wait']:.2f} min")
                    st.caption(f"{row['People waiting']} people currently waiting")
    elif all(
        not counter.get("is_active") for counter in counters
    ):
        st.info("There are no active counters to estimate right now.")
    else:
        st.info("No active counter currently has a valid prediction.")


def render_admin_dashboard() -> None:
    """Render the authenticated SmartQueue administration interface."""
    try:
        db.initialize_database()
    except RuntimeError as exc:
        st.error(str(exc))
        st.info(
            "Configure the initial admin using the SMARTQUEUE_ADMIN_USERNAME and "
            "SMARTQUEUE_ADMIN_PASSWORD environment variables, then reload."
        )
    except db.DatabaseOperationError as exc:
        st.error(f"Could not initialize the database: {exc}")

    if not _show_login():
        return

    with st.sidebar:
        st.markdown("### SmartQueue Admin")
        st.caption(f"Signed in as {st.session_state.get('admin_username', 'admin')}")
        st.caption("OPERATIONS")
        page = st.radio(
            "Admin workspace",
            ["Overview", "Counter Management", "Queue Management", "Waiting Time Estimates"],
            key="smartqueue_admin_navigation",
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Log out", key="admin_dashboard_logout", width="stretch"):
            st.session_state["admin_authenticated"] = False
            st.session_state.pop("admin_username", None)
            st.rerun()

    counters = _load_counters()
    if counters is None:
        return
    if page == "Overview":
        _render_overview(counters)
    elif page == "Counter Management":
        _render_counter_management(counters)
    elif page == "Queue Management":
        _render_queue_management(counters)
    else:
        _render_predictions(counters)