import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.db import supabase


def show():
    st.title("📈 DCF Valuations")

    # Pull all DCF models
    dcf_data = supabase.table("dcf_models") \
        .select("*") \
        .order("run_date", desc=True) \
        .execute()

    if not dcf_data.data:
        st.info("No DCF models yet — run phase 2 first")
        return

    # Get most recent run per ticker
    seen = set()
    latest_models = []
    for model in dcf_data.data:
        ticker = model.get("ticker")
        if ticker not in seen:
            seen.add(ticker)
            latest_models.append(model)

    # ─── SUMMARY TABLE ────────────────────────────────────
    st.subheader("Latest Valuations")

    rows = []
    for m in latest_models:
        ticker = m.get("ticker", "")
        current = m.get("current_price", 0) or 0
        bear = m.get("bear_implied_price", 0) or 0
        base = m.get("base_implied_price", 0) or 0
        bull = m.get("bull_implied_price", 0) or 0

        bear_up = ((bear - current) / current * 100) if current else 0
        base_up = ((base - current) / current * 100) if current else 0
        bull_up = ((bull - current) / current * 100) if current else 0

        rows.append({
            "Ticker": ticker,
            "Current Price": f"${current:.2f}",
            "Bear Case": f"${bear:.2f} ({bear_up:+.1f}%)",
            "Base Case": f"${base:.2f} ({base_up:+.1f}%)",
            "Bull Case": f"${bull:.2f} ({bull_up:+.1f}%)",
            "Run Date": m.get("run_date", "")[:10],
            "base_upside": base_up
        })

    df = pd.DataFrame(rows)

    # Colour the base upside column
    def colour_upside(val):
        try:
            num = float(str(val).replace("%", "").split("(")[1].replace(")", "").replace("+", ""))
            color = "color: green" if num > 0 else "color: red"
            return color
        except:
            return ""

    st.dataframe(
        df.drop(columns=["base_upside"]),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # ─── UPSIDE CHART ─────────────────────────────────────
    st.subheader("Base Case Upside vs Current Price")

    tickers = [r["Ticker"] for r in rows]
    upsides = [r["base_upside"] for r in rows]
    colors = ["green" if u > 0 else "red" for u in upsides]

    fig = go.Figure(go.Bar(
        x=tickers,
        y=upsides,
        marker_color=colors,
        text=[f"{u:+.1f}%" for u in upsides],
        textposition="outside"
    ))
    fig.update_layout(
        yaxis_title="Base Case Upside/Downside (%)",
        height=400,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(zeroline=True, zerolinecolor="white", zerolinewidth=2)
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ─── DETAILED VIEW ────────────────────────────────────
    st.subheader("Detailed Assumptions")

    selected = st.selectbox("Select company", [r["Ticker"] for r in rows])
    model = next((m for m in latest_models if m.get("ticker") == selected), None)

    if model and model.get("assumptions"):
        assumptions = model["assumptions"]
        for scenario in ["bear", "base", "bull"]:
            a = assumptions.get(scenario, {})
            if not a:
                continue
            with st.expander(f"{scenario.upper()} CASE — Implied ${model.get(f'{scenario}_implied_price', 0):.2f}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Rev Growth Yr 1-3", f"{a.get('rev_growth_yr1_3', 0):.1f}%")
                col1.metric("Rev Growth Yr 4-5", f"{a.get('rev_growth_yr4_5', 0):.1f}%")
                col2.metric("FCF Margin", f"{a.get('fcf_margin', 0):.1f}%")
                col2.metric("Terminal Growth", f"{a.get('terminal_growth', 0):.1f}%")
                col3.metric("WACC", f"{a.get('wacc', 0):.1f}%")
                st.write(f"**Rationale:** {a.get('rationale', 'N/A')}")