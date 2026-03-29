from utils.db import supabase
from datetime import datetime


def store_dcf_results(ticker, metrics, assumptions, results, current_price):
    """Save a DCF run to the database for tracking over time."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        print(f"  {ticker} not found in companies table")
        return

    company_id = company.data[0]["id"]

    def upside(implied):
        if current_price and implied:
            return ((implied - current_price) / current_price) * 100
        return 0

    bear = results.get("bear", {})
    base = results.get("base", {})
    bull = results.get("bull", {})

    supabase.table("dcf_models").insert({
        "company_id": company_id,
        "ticker": ticker,
        "run_date": datetime.now().isoformat(),
        "last_revenue": int(metrics["last_revenue"]),
        "shares_outstanding": 0,
        "current_price": current_price,
        "bear_implied_price": bear.get("implied_price", 0),
        "base_implied_price": base.get("implied_price", 0),
        "bull_implied_price": bull.get("implied_price", 0),
        "bear_upside_pct": upside(bear.get("implied_price", 0)),
        "base_upside_pct": upside(base.get("implied_price", 0)),
        "bull_upside_pct": upside(bull.get("implied_price", 0)),
        "assumptions": assumptions,
        "metrics": {k: float(v) if v else 0 for k, v in metrics.items()}
    }).execute()

    print(f"  ✅ DCF stored in database")