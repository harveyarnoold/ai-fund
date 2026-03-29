import streamlit as st
from datetime import datetime
from utils.db import supabase


def show():
    st.title("🚨 Alerts Centre")

    # ─── FILTERS ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        show_read = st.checkbox("Show read alerts", value=False)
    with col2:
        companies = supabase.table("companies").select("ticker").execute()
        tickers = ["All"] + [c["ticker"] for c in companies.data]
        selected_ticker = st.selectbox("Filter by company", tickers)
    with col3:
        alert_types = ["All", "filing_flag", "urgent_news", "fcf_margin_drop",
                       "revenue_decline", "competitor_pricing_change",
                       "executive_change", "extreme_retail_hype"]
        selected_type = st.selectbox("Filter by type", alert_types)

    st.markdown("---")

    # ─── BUILD QUERY ──────────────────────────────────────
    query = supabase.table("alerts") \
        .select("*, companies(ticker, name)") \
        .order("created_at", desc=True)

    if not show_read:
        query = query.eq("is_read", False)

    alerts = query.limit(50).execute()
    data = alerts.data or []

    # Filter by ticker client-side
    if selected_ticker != "All":
        data = [a for a in data if a.get("companies", {}).get("ticker") == selected_ticker]

    # Filter by type client-side
    if selected_type != "All":
        data = [a for a in data if a.get("alert_type") == selected_type]

    # ─── DISPLAY ──────────────────────────────────────────
    if not data:
        st.success("✅ No alerts match your filters")
        return

    st.caption(f"Showing {len(data)} alert(s)")

    for alert in data:
        ticker = alert.get("companies", {}).get("ticker", "?")
        company_name = alert.get("companies", {}).get("name", "")
        alert_type = alert.get("alert_type", "").replace("_", " ").upper()
        message = alert.get("message", "")
        created = alert.get("created_at", "")[:16].replace("T", " ")
        is_read = alert.get("is_read", False)
        alert_id = alert.get("id")

        # Pick colour based on urgency
        urgent_types = ["urgent_news", "filing_flag", "fcf_margin_drop"]
        if alert.get("alert_type") in urgent_types:
            container = st.error
        else:
            container = st.warning

        with st.expander(f"{'✅' if is_read else '🔴'} [{ticker}] {alert_type} — {created}"):
            st.write(f"**Company:** {company_name} ({ticker})")
            st.write(f"**Type:** {alert_type}")
            st.write(f"**Message:** {message}")
            st.caption(f"Created: {created}")

            if not is_read:
                if st.button(f"Mark as Read", key=f"read_{alert_id}"):
                    supabase.table("alerts").update(
                        {"is_read": True}
                    ).eq("id", alert_id).execute()
                    st.success("Marked as read")
                    st.rerun()