
import streamlit as st
from database.db import initialize_database
from modules.admin import render_admin_dashboard

# Initialize database
initialize_database()

# Display admin dashboard
render_admin_dashboard()
