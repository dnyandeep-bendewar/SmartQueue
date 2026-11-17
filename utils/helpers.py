"""Shared presentation helpers for the SmartQueue Streamlit application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st


THEME_STATE_KEY = "smartqueue_theme"
THEME_TOGGLE_KEY = "smartqueue_theme_toggle"
_THEME_STYLESHEET = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
_THEME_VARIABLES_MARKER = "/* SMARTQUEUE_THEME_VARIABLES */"

THEMES: dict[str, dict[str, str]] = {
    "Light": {
        "background": "#F8FAFC",
        "sidebar": "#FFFFFF",
        "surface": "#FFFFFF",
        "input": "#FFFFFF",
        "primary": "#0F172A",
        "accent": "#0D9488",
        "accent_text": "#0F766E",
        "accent_hover": "#0F766E",
        "text": "#0F172A",
        "secondary_text": "#64748B",
        "border": "#E2E8F0",
        "button_text": "#0F172A",
        "button_hover_text": "#FFFFFF",
        "shadow": "rgba(15, 23, 42, 0.06)",
        "color_scheme": "light",
    },
    "Dark": {
        "background": "#0B1220",
        "sidebar": "#111C2E",
        "surface": "#151F32",
        "input": "#1B2940",
        "primary": "#F8FAFC",
        "accent": "#2DD4BF",
        "accent_text": "#2DD4BF",
        "accent_hover": "#14B8A6",
        "text": "#F8FAFC",
        "secondary_text": "#A8B5C8",
        "border": "#29364B",
        "button_text": "#0B1220",
        "button_hover_text": "#0B1220",
        "shadow": "rgba(0, 0, 0, 0.22)",
        "color_scheme": "dark",
    },
}


def initialize_theme_state() -> None:
    """Set the default Light theme and initialize its sidebar toggle once."""
    if THEME_STATE_KEY not in st.session_state:
        st.session_state[THEME_STATE_KEY] = "Light"
    if THEME_TOGGLE_KEY not in st.session_state:
        st.session_state[THEME_TOGGLE_KEY] = (
            st.session_state[THEME_STATE_KEY] == "Dark"
        )


def get_current_theme() -> str:
    """Return the selected theme, falling back to Light for invalid session data."""
    theme = st.session_state.get(THEME_STATE_KEY, "Light")
    return theme if theme in THEMES else "Light"


def apply_theme_stylesheet(theme: str | None = None) -> None:
    """Inject shared CSS with palette variables for the selected theme."""
    selected_theme = theme or get_current_theme()
    if selected_theme not in THEMES:
        raise ValueError(f"Unknown SmartQueue theme: {selected_theme!r}.")

    stylesheet = _THEME_STYLESHEET.read_text(encoding="utf-8")
    if _THEME_VARIABLES_MARKER not in stylesheet:
        raise RuntimeError(
            f"Theme variables marker is missing from {_THEME_STYLESHEET}."
        )

    css_names = {
        "background": "bg",
        "sidebar": "sidebar",
        "surface": "surface",
        "input": "input",
        "primary": "primary",
        "accent": "accent",
        "accent_text": "accent-text",
        "accent_hover": "accent-hover",
        "text": "text",
        "secondary_text": "secondary-text",
        "border": "border",
        "button_text": "button-text",
        "button_hover_text": "button-hover-text",
        "shadow": "shadow",
        "color_scheme": "color-scheme",
    }
    variable_block = ":root {\n" + "\n".join(
        f"  --sq-{css_name}: {THEMES[selected_theme][theme_name]};"
        for theme_name, css_name in css_names.items()
    ) + "\n}"
    st.markdown(
        f"<style>{stylesheet.replace(_THEME_VARIABLES_MARKER, variable_block)}</style>",
        unsafe_allow_html=True,
    )


def get_plotly_theme() -> dict[str, Any]:
    """Return Plotly layout settings matching the currently selected theme."""
    palette = THEMES[get_current_theme()]
    colors = (
        [palette["accent"], "#2563EB", "#B45309", "#7C3AED", "#DC2626"]
        if get_current_theme() == "Light"
        else [palette["accent"], "#60A5FA", "#FBBF24", "#C4B5FD", "#FDA4AF"]
    )
    return {
        "template": "plotly_white" if get_current_theme() == "Light" else "plotly_dark",
        "colorway": colors,
        "paper_bgcolor": palette["background"],
        "plot_bgcolor": palette["surface"],
        "font": {"color": palette["text"]},
        "legend": {"font": {"color": palette["text"]}},
        "xaxis": {
            "gridcolor": palette["border"],
            "zerolinecolor": palette["border"],
            "tickfont": {"color": palette["secondary_text"]},
            "title": {"font": {"color": palette["text"]}},
        },
        "yaxis": {
            "gridcolor": palette["border"],
            "zerolinecolor": palette["border"],
            "tickfont": {"color": palette["secondary_text"]},
            "title": {"font": {"color": palette["text"]}},
        },
    }