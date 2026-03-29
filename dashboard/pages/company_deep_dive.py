import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from utils.db import supabase


def show():
    st.title("🏢 Company Deep Dive")

    # Company selector
    companies = supabase.table("companies").select("*").execute()
    if not companies.data:
        st.info("No companies in watchlist yet")
        return

    company_map = {c["ticker"]: c for c in companies.data}
    selected_ticker = st.selectbox(
        "Select Company",
        list(company_map.keys())
    )

    company = company_map[selected_ticker]
    company_id = company["id"]

    st.markdown(f"### {company.get('name', selected_ticker)} `{selected_ticker}`")
    st.caption(f"Sector: {company.get('sector', 'N/A')}")
    st.markdown("---")

    # ─── TABS ─────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Financials & DCF",
        "🚨 Alerts",
        "📄 Research",
        "📈 Sentiment History"
    ])

    # ── TAB 1: FINANCIALS ─────────────────────────────────
    with tab1:
        dcf_data = supabase.table("dcf_models") \
            .select("*") \
            .eq("ticker", selected_ticker) \
            .order("run_date", desc=True) \
            .limit(1) \
            .execute()

        if dcf_data.data:
            m = dcf_data.data[0]
            current = m.get("current_price", 0) or 0
            bear = m.get("bear_implied_price", 0) or 0
            base = m.get("base_implied_price", 0) or 0
            bull = m.get("bull_implied_price", 0) or 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current Price", f"${current:.2f}")
            col2.metric("Bear Case", f"${bear:.2f}",
                        f"{((bear-current)/current*100):+.1f}%" if current else "N/A")
            col3.metric("Base Case", f"${base:.2f}",
                        f"{((base-current)/current*100):+.1f}%" if current else "N/A")
            col4.metric("Bull Case", f"${bull:.2f}",
                        f"{((bull-current)/current*100):+.1f}%" if current else "N/A")

            # Waterfall chart
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Implied Prices",
                x=["Bear", "Base", "Bull", "Current"],
                y=[bear, base, bull, current],
                marker_color=["#ef5350", "#42a5f5", "#66bb6a", "#ffffff"],
                text=[f"${v:.2f}" for v in [bear, base, bull, current]],
                textposition="outside"
            ))
            fig.update_layout(
                title="DCF Implied Price vs Current",
                yaxis_title="Price (USD)",
                height=400,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)

            # Assumptions detail
            if m.get("assumptions"):
                st.subheader("Model Assumptions")
                assumptions = m["assumptions"]
                for scenario in ["bear", "base", "bull"]:
                    a = assumptions.get(scenario, {})
                    if a:
                        with st.expander(f"{scenario.upper()}"):
                            st.write(f"Revenue growth yr 1-3: **{a.get('rev_growth_yr1_3', 0):.1f}%**")
                            st.write(f"Revenue growth yr 4-5: **{a.get('rev_growth_yr4_5', 0):.1f}%**")
                            st.write(f"FCF margin: **{a.get('fcf_margin', 0):.1f}%**")
                            st.write(f"WACC: **{a.get('wacc', 0):.1f}%**")
                            st.write(f"Terminal growth: **{a.get('terminal_growth', 0):.1f}%**")
                            st.write(f"Rationale: {a.get('rationale', 'N/A')}")
        else:
            st.info("No DCF data yet — run Phase 2 first")

    # ── TAB 2: ALERTS ─────────────────────────────────────
    with tab2:
        alerts = supabase.table("alerts") \
            .select("*") \
            .eq("company_id", company_id) \
            .order("created_at", desc=True) \
            .limit(20) \
            .execute()

        if alerts.data:
            for alert in alerts.data:
                alert_type = alert.get("alert_type", "").replace("_", " ").upper()
                message = alert.get("message", "")
                created = alert.get("created_at", "")[:16].replace("T", " ")
                is_read = alert.get("is_read", False)

                prefix = "✅" if is_read else "🔴"
                with st.expander(f"{prefix} {alert_type} — {created}"):
                    st.write(message)
                    if not is_read:
                        if st.button("Mark Read", key=f"dr_{alert['id']}"):
                            supabase.table("alerts").update(
                                {"is_read": True}
                            ).eq("id", alert["id"]).execute()
                            st.rerun()
        else:
            st.success("No alerts for this company")

    # ── TAB 3: RESEARCH ───────────────────────────────────
    with tab3:
        docs = supabase.table("documents") \
            .select("*, analysis(summary, sentiment_score, flags)") \
            .eq("company_id", company_id) \
            .order("ingested_at", desc=True) \
            .limit(20) \
            .execute()

        if docs.data:
            for doc in docs.data:
                doc_type = doc.get("doc_type", "").upper()
                title = doc.get("title", "")[:60]
                date = doc.get("ingested_at", "")[:10]
                analyses = doc.get("analysis", [])
                analysis = analyses[0] if analyses else {}
                summary = analysis.get("summary", "")
                sentiment = analysis.get("sentiment_score", 0)

                with st.expander(f"[{doc_type}] {title} — {date}"):
                    if summary:
                        st.write(f"**Summary:** {summary}")
                    st.metric("Sentiment", f"{sentiment:.2f}")
                    flags = analysis.get("flags", []) or []
                    if flags:
                        st.error(f"Flags: {', '.join(flags)}")
        else:
            st.info("No research documents yet")

    # ── TAB 4: SENTIMENT HISTORY ──────────────────────────
    with tab4:
        month_ago = (datetime.now() - timedelta(days=30)).isoformat()
        analysis_data = supabase.table("analysis") \
            .select("sentiment_score, created_at, documents(doc_type)") \
            .gte("created_at", month_ago) \
            .execute()

        # Filter to this company's docs
        company_docs = supabase.table("documents") \
            .select("id, doc_type") \
            .eq("company_id", company_id) \
            .execute()
        company_doc_ids = {d["id"] for d in company_docs.data}

        all_analysis = supabase.table("analysis") \
            .select("*, document_id, documents(doc_type, company_id)") \
            .gte("created_at", month_ago) \
            .execute()

        filtered = [
            a for a in all_analysis.data
            if a.get("documents", {}).get("company_id") == company_id
        ]

        if filtered:
            df = pd.DataFrame([{
                "date": a["created_at"][:10],
                "sentiment": a["sentiment_score"],
                "type": a.get("documents", {}).get("doc_type", "")
            } for a in filtered])

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["date"],
                y=df["sentiment"],
                mode="markers+lines",
                marker=dict(
                    color=df["sentiment"].apply(lambda x: "green" if x > 0 else "red"),
                    size=8
                ),
                line=dict(color="gray", width=1)
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
            fig.update_layout(
                title=f"{selected_ticker} Sentiment Over Time",
                yaxis_title="Sentiment Score",
                height=400,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data yet for sentiment history")