import streamlit as st
from datetime import datetime, timedelta
from utils.db import supabase

def show():
    # TEMPORARY DEBUG — remove after fixing
    try:
        st.write("URL:", st.secrets["SUPABASE_URL"])
        st.write("Key starts with:", st.secrets["SUPABASE_KEY"][:20])
    except Exception as e:
        st.error(f"Secret error: {e}")
import streamlit as st
from datetime import datetime, timedelta
from utils.db import supabase


def show():
    st.title("🏠 Portfolio Intelligence Overview")
    st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ─── TOP METRICS ROW ──────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)

    # Unread alerts
    alerts = supabase.table("alerts").select("*").eq("is_read", False).execute()
    col1.metric("🚨 Unread Alerts", len(alerts.data))

    # Companies tracked
    companies = supabase.table("companies").select("*").execute()
    col2.metric("🏢 Companies Tracked", len(companies.data))

    # Documents ingested today
    today = datetime.now().strftime("%Y-%m-%d")
    docs_today = supabase.table("documents").select("*").gte("ingested_at", today).execute()
    col3.metric("📄 Docs Today", len(docs_today.data))

    # Documents this week
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    docs_week = supabase.table("documents").select("*").gte("ingested_at", week_ago).execute()
    col4.metric("📚 Docs This Week", len(docs_week.data))

    # DCF models run
    dcf_count = supabase.table("dcf_models").select("*").execute()
    col5.metric("📊 DCF Models Run", len(dcf_count.data))

    st.markdown("---")

    # ─── ALERTS PREVIEW ───────────────────────────────────
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("🚨 Latest Alerts")
        recent_alerts = supabase.table("alerts") \
            .select("*, companies(ticker)") \
            .eq("is_read", False) \
            .order("created_at", desc=True) \
            .limit(5) \
            .execute()

        if recent_alerts.data:
            for alert in recent_alerts.data:
                ticker = alert.get("companies", {}).get("ticker", "?")
                alert_type = alert.get("alert_type", "").replace("_", " ").upper()
                message = alert.get("message", "")[:80]
                created = alert.get("created_at", "")[:10]

                if "urgent" in alert.get("alert_type", "").lower():
                    st.error(f"**[{ticker}]** {alert_type}\n{message}")
                elif "flag" in alert.get("alert_type", "").lower():
                    st.warning(f"**[{ticker}]** {alert_type}\n{message}")
                else:
                    st.info(f"**[{ticker}]** {alert_type}\n{message}")
        else:
            st.success("✅ No unread alerts — all clear")

    with col_right:
        st.subheader("📄 Recent Documents Ingested")
        recent_docs = supabase.table("documents") \
            .select("*, companies(ticker)") \
            .order("ingested_at", desc=True) \
            .limit(8) \
            .execute()

        if recent_docs.data:
            for doc in recent_docs.data:
                ticker = doc.get("companies", {}).get("ticker", "?")
                doc_type = doc.get("doc_type", "").replace("_", " ").upper()
                title = doc.get("title", "")[:50]
                date = doc.get("ingested_at", "")[:10]
                st.caption(f"`{ticker}` · {doc_type} · {date}")
                st.write(f"↳ {title}")
        else:
            st.info("No documents yet — run the pipeline first")

    st.markdown("---")

    # ─── SENTIMENT OVERVIEW ───────────────────────────────
    st.subheader("📊 Sentiment Snapshot (Last 7 Days)")

    analysis_data = supabase.table("analysis") \
        .select("*, documents(doc_type, companies(ticker))") \
        .gte("created_at", week_ago) \
        .execute()

    if analysis_data.data:
        import pandas as pd

        rows = []
        for a in analysis_data.data:
            doc = a.get("documents") or {}
            company = doc.get("companies") or {}
            ticker = company.get("ticker", "Unknown")
            rows.append({
                "ticker": ticker,
                "doc_type": doc.get("doc_type", ""),
                "sentiment": a.get("sentiment_score", 0)
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            avg_sentiment = df.groupby("ticker")["sentiment"].mean().reset_index()
            avg_sentiment.columns = ["Ticker", "Avg Sentiment"]
            avg_sentiment["Avg Sentiment"] = avg_sentiment["Avg Sentiment"].round(3)
            avg_sentiment = avg_sentiment.sort_values("Avg Sentiment", ascending=False)

            import plotly.graph_objects as go
            colors = ["green" if s > 0 else "red" for s in avg_sentiment["Avg Sentiment"]]
            fig = go.Figure(go.Bar(
                x=avg_sentiment["Ticker"],
                y=avg_sentiment["Avg Sentiment"],
                marker_color=colors
            ))
            fig.update_layout(
                title="Average Sentiment Score by Company (7 days)",
                yaxis_title="Sentiment (-1 = Bearish, +1 = Bullish)",
                height=350,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No analysis data yet — run the pipeline to populate this chart")