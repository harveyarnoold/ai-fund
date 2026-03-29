import streamlit as st
import sys
import os

# This fixes the import issue on Windows
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="AI Fund Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.sidebar.title("📊 AI Fund Intelligence")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "🏠  Overview",
        "🚨  Alerts",
        "📈  DCF Valuations",
        "📄  Research Feed",
        "🏢  Company Deep Dive",
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("Pipeline runs daily at 7:00 AM AEST")

if page == "🏠  Overview":
    from dashboard.pages.overview import show
    show()

elif page == "🚨  Alerts":
    from dashboard.pages.alerts import show
    show()

elif page == "📈  DCF Valuations":
    from dashboard.pages.dcf import show
    show()

elif page == "📄  Research Feed":
    from dashboard.pages.research_feed import show
    show()

elif page == "🏢  Company Deep Dive":
    from dashboard.pages.company_deep_dive import show
    show()