"""Main Streamlit application entry point for SmartQueue."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

import streamlit as st

from database import db
from modules.admin import render_admin_dashboard
from modules.analytics import render_analytics_dashboard
from modules.visitor import render_visitor_portal
from utils.helpers import (
    THEME_STATE_KEY,
    THEME_TOGGLE_KEY,
    apply_theme_stylesheet,
    get_current_theme,
    initialize_theme_state,
)


_ADMIN_AUTHENTICATED_KEY = "admin_authenticated"
_ADMIN_USERNAME_KEY = "admin_username"
_ADMIN_PROOF_KEY = "_smartqueue_admin_auth_proof"
_ADMIN_PAGES = {"Admin Dashboard", "Analytics Dashboard"}


@st.cache_resource
def _admin_proof_secret() -> bytes:
    """Keep the signing key stable across Streamlit reruns without exposing it to clients."""
    return secrets.token_bytes(32)


def _clear_admin_authentication() -> None:
    """Clear all SmartQueue admin session credentials."""
    st.session_state[_ADMIN_AUTHENTICATED_KEY] = False
    st.session_state.pop(_ADMIN_USERNAME_KEY, None)
    st.session_state.pop(_ADMIN_PROOF_KEY, None)


def _set_admin_authentication(username: str) -> None:
    """Store an admin session marker signed with a server-only process secret."""
    proof = hmac.new(
        _admin_proof_secret(),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    st.session_state[_ADMIN_AUTHENTICATED_KEY] = True
    st.session_state[_ADMIN_USERNAME_KEY] = username
    st.session_state[_ADMIN_PROOF_KEY] = proof


def _has_valid_admin_authentication() -> bool:
    """Require a server-signed proof in addition to the session authentication flag."""
    username = st.session_state.get(_ADMIN_USERNAME_KEY)
    proof = st.session_state.get(_ADMIN_PROOF_KEY)
    if (
        st.session_state.get(_ADMIN_AUTHENTICATED_KEY) is not True
        or not isinstance(username, str)
        or not isinstance(proof, str)
    ):
        return False

    expected_proof = hmac.new(
        _admin_proof_secret(),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(proof, expected_proof):
        _clear_admin_authentication()
        return False
    return True


def _render_admin_login() -> bool:
    """Authenticate the current session before rendering protected dashboards."""
    if _has_valid_admin_authentication():
        return True

    st.title("Admin sign in")
    st.caption("Admin credentials are required for the Admin and Analytics dashboards.")
    with st.form("app_admin_login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Log in", type="primary")

    if not submitted:
        return False

    normalized_username = username.strip()
    if not normalized_username or not password:
        st.error("Enter both a username and password.")
        return False

    try:
        authenticated = db.authenticate_admin(normalized_username, password)
    except (db.DatabaseOperationError, sqlite3.Error, OSError) as exc:
        st.error(f"Could not authenticate against the database: {exc}")
        return False

    if not authenticated:
        _clear_admin_authentication()
        st.error("The username or password is incorrect.")
        return False

    _set_admin_authentication(normalized_username)
    st.rerun()
    return True


def _navigate_to(page: str) -> None:
    """Route Home-page actions through the existing global navigation widget."""
    st.session_state["smartqueue_navigation"] = page


def _render_home() -> None:
    with st.container(border=True):
        hero_columns = st.columns([1.5, 1], gap="large")
        with hero_columns[0]:
            st.markdown(
                '<p class="sq-home-eyebrow">SMARTER QUEUE OPERATIONS</p>',
                unsafe_allow_html=True,
            )
            st.title("SmartQueue")
            st.subheader("AI-Based Queue Waiting Time Prediction and Management System")
            st.write(
                "Long, uncertain queues make service harder for visitors and staff. "
                "SmartQueue brings queue estimates, digital tokens and counter "
                "management together in one clear experience."
            )
            action_columns = st.columns(2)
            action_columns[0].button(
                "Open Visitor Portal",
                key="home_hero_visitor",
                type="primary",
                on_click=_navigate_to,
                args=("Visitor Portal",),
                width="stretch",
            )
            action_columns[1].button(
                "Admin Dashboard",
                key="home_hero_admin",
                on_click=_navigate_to,
                args=("Admin Dashboard",),
                width="stretch",
            )
        with hero_columns[1]:
            st.markdown("### A clearer visit, step by step")
            st.markdown("**01**  Choose the service you need")
            st.markdown("**02**  Receive a digital queue token")
            st.markdown("**03**  Track your status and estimated wait")
            st.caption("Visitor access is open. Admin tools require sign-in.")

    st.markdown("## Quick navigation")
    navigation_cards = st.columns(3, gap="medium")
    cards = [
        (
            "Visitor Portal",
            "Join and follow a queue",
            "Select a service, compare waiting times, then generate and track a digital token.",
            "Open Visitor Portal",
            "Visitor Portal",
        ),
        (
            "Admin Dashboard",
            "Manage daily operations",
            "Manage service counters, monitor visitors and update token status.",
            "Open Admin Dashboard",
            "Admin Dashboard",
        ),
        (
            "Analytics Dashboard",
            "Understand queue activity",
            "Review queue statistics, explore service trends and monitor waiting-time predictions.",
            "Open Analytics",
            "Analytics Dashboard",
        ),
    ]
    for column, (title, subtitle, description, button_label, route) in zip(
        navigation_cards, cards
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"### {title}")
                st.caption(subtitle)
                st.write(description)
                column.button(
                    button_label,
                    key=f"home_nav_{route.lower().replace(' ', '_')}",
                    on_click=_navigate_to,
                    args=(route,),
                    type="primary" if route == "Visitor Portal" else "secondary",
                    width="stretch",
                )

    st.markdown("## How SmartQueue works")
    steps = st.columns(3, gap="medium")
    for column, number, title, description in zip(
        steps,
        ("01", "02", "03"),
        ("Choose a service", "Receive a token", "Track your status"),
        (
            "Compare active counters and their predicted waits.",
            "Take a digital token for the counter that suits you.",
            "Use your secure tracking reference to check queue progress.",
        ),
    ):
        with column:
            with st.container(border=True):
                st.markdown(f'<p class="sq-home-step">{number}</p>', unsafe_allow_html=True)
                st.markdown(f"### {title}")
                st.write(description)

    st.markdown("## Built for the whole queue journey")
    features = [
        ("Waiting-time prediction", "Machine-learning estimates based on queue conditions."),
        ("Counter recommendation", "Compare predicted waits to help choose a counter."),
        ("Digital tokens", "Generate queue tokens for supported services."),
        ("Secure tracking", "Check token status using a private tracking reference."),
        ("Queue management", "Let administrators manage counters and token statuses."),
        ("Analytics dashboard", "Review current queue statistics and recorded trends."),
    ]
    feature_columns = st.columns(3, gap="medium")
    for index, (title, description) in enumerate(features):
        with feature_columns[index % len(feature_columns)]:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(description)

    st.markdown("## System overview")
    try:
        statistics = db.get_queue_statistics()
    except db.DatabaseOperationError as exc:
        st.info(f"Queue statistics are unavailable right now: {exc}")
    else:
        metric_columns = st.columns(3, gap="medium")
        metric_columns[0].metric("Active service counters", int(statistics["active_counters"]))
        metric_columns[1].metric(
            "Currently waiting visitors",
            int(statistics["waiting_tokens"]),
        )
        metric_columns[2].metric(
            "Visitors ever served",
            int(statistics["historically_served_tokens"]),
        )
        if int(statistics["total_counters"]) == 0:
            st.info("No service counters have been configured yet.")
        elif (
            int(statistics["waiting_tokens"]) == 0
            and int(statistics["historically_served_tokens"]) == 0
        ):
            st.info("There is no visitor activity recorded yet.")

    st.divider()
    st.markdown(
        '<div class="sq-home-footer"><strong>SmartQueue</strong><br>'
        "AI-Based Queue Waiting Time Prediction and Management System<br>"
        '<span>Built using Python, Streamlit, SQLite and Scikit-learn.</span></div>',
        unsafe_allow_html=True,
    )


def main() -> None:
    """Initialize shared services, route pages, and enforce admin authorization."""
    st.set_page_config(
        page_title="SmartQueue",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_theme_state()

    initialization_error: str | None = None
    admin_setup_error: str | None = None
    try:
        db.initialize_database()
    except (db.DatabaseOperationError, sqlite3.Error, OSError) as exc:
        initialization_error = str(exc)
    except RuntimeError as exc:
        admin_setup_error = str(exc)

    with st.sidebar:
        st.title("SmartQueue")
        is_dark_mode = st.toggle("Dark mode", key=THEME_TOGGLE_KEY)
        selected_theme = "Dark" if is_dark_mode else "Light"
        st.session_state[THEME_STATE_KEY] = selected_theme
        page = st.radio(
            "Navigation",
            ["Home", "Visitor Portal", "Admin Dashboard", "Analytics Dashboard"],
            key="smartqueue_navigation",
        )
        if _has_valid_admin_authentication():
            st.caption(f"Signed in as {st.session_state[_ADMIN_USERNAME_KEY]}")
            if st.button("Log out", key="smartqueue_logout", width="stretch"):
                _clear_admin_authentication()
                st.rerun()
        else:
            st.caption("Visitor access is open; admin dashboards require sign-in.")

    apply_theme_stylesheet(get_current_theme())

    if initialization_error is not None:
        st.error(f"Could not initialize the SmartQueue database: {initialization_error}")
        if page != "Home":
            st.info("Database-backed pages are unavailable until the database issue is resolved.")
            return

    if admin_setup_error is not None and page in _ADMIN_PAGES:
        st.error(admin_setup_error)
        st.info(
            "Configure SMARTQUEUE_ADMIN_USERNAME and SMARTQUEUE_ADMIN_PASSWORD "
            "for the initial admin account, then reload the application."
        )
        return

    if page == "Home":
        _render_home()
    elif page == "Visitor Portal":
        render_visitor_portal()
    elif page in _ADMIN_PAGES:
        if not _render_admin_login():
            return
        if page == "Admin Dashboard":
            render_admin_dashboard()
        else:
            render_analytics_dashboard()


if __name__ == "__main__":
    main()