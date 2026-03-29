import streamlit as st
from datetime import datetime, timedelta
from utils.db import supabase


DOC_TYPE_EMOJI = {
    "earnings_transcript": "🎙️",
    "news": "📰",
    "10-K": "📋",
    "10-Q": "📋",
    "8-K": "⚡",
    "reddit_sentiment": "📱",
    "hiring_analysis": "💼",
    "app_review_analysis": "⭐",
    "patent_analysis": "🔬",
    "executive_changes": "👤",
    "competitor_pricing": "🏢",
    "competitor_change_analysis": "🔔",
}


def show():
    st.title("📄 Research Feed")

    # ─── FILTERS ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        companies = supabase.table("companies").select("ticker").execute()
        tickers = ["All"] + [c["ticker"] for c in companies.data]
        selected_ticker = st.selectbox("Company", tickers)

    with col2:
        doc_types = ["All", "news", "8-K", "10-Q", "earnings_transcript",
                     "hiring_analysis", "app_review_analysis",
                     "patent_analysis", "executive_changes",
                     "competitor_change_analysis", "reddit_sentiment"]
        selected_type = st.selectbox("Document Type", doc_types)

    with col3:
        time_options = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30, "All time": 3650}
        selected_time = st.selectbox("Time Range", list(time_options.keys()))

    days_back = time_options[selected_time]
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

    st.markdown("---")

    # ─── FETCH DOCUMENTS ──────────────────────────────────
    query = supabase.table("documents") \
        .select("*, companies(ticker, name), analysis(summary, sentiment_score, flags, thesis_tags)") \
        .gte("ingested_at", cutoff) \
        .order("ingested_at", desc=True) \
        .limit(50)

    docs = query.execute()
    data = docs.data or []

    # Filter client side
    if selected_ticker != "All":
        data = [d for d in data if d.get("companies", {}).get("ticker") == selected_ticker]
    if selected_type != "All":
        data = [d for d in data if d.get("doc_type") == selected_type]

    if not data:
        st.info("No documents match your filters")
        return

    st.caption(f"Showing {len(data)} document(s)")

    # ─── DISPLAY FEED ─────────────────────────────────────
    for doc in data:
        ticker = doc.get("companies", {}).get("ticker", "?")
        doc_type = doc.get("doc_type", "")
        emoji = DOC_TYPE_EMOJI.get(doc_type, "📄")
        title = doc.get("title", "Untitled")
        ingested = doc.get("ingested_at", "")[:16].replace("T", " ")
        url = doc.get("source_url", "")

        # Get analysis if available
        analyses = doc.get("analysis", [])
        analysis = analyses[0] if analyses else {}
        summary = analysis.get("summary", "")
        sentiment = analysis.get("sentiment_score", 0)
        flags = analysis.get("flags", []) or []
        tags = analysis.get("thesis_tags", []) or []

        # Sentiment colour
        if sentiment > 0.3:
            sentiment_label = f"🟢 {sentiment:.2f}"
        elif sentiment < -0.3:
            sentiment_label = f"🔴 {sentiment:.2f}"
        else:
            sentiment_label = f"🟡 {sentiment:.2f}"

        with st.expander(f"{emoji} [{ticker}] {title[:70]} — {ingested}"):
            col1, col2 = st.columns([3, 1])

            with col1:
                if summary:
                    st.write(f"**AI Summary:** {summary}")
                else:
                    content = doc.get("content", "")
                    if content:
                        st.write(content[:300] + "...")

            with col2:
                st.metric("Sentiment", sentiment_label)
                if url:
                    st.link_button("View Source", url)

            if flags:
                st.error(f"🚩 Flags: {', '.join(flags)}")

            if tags:
                tag_str = " · ".join([f"`{t}`" for t in tags[:5]])
                st.caption(f"Tags: {tag_str}")