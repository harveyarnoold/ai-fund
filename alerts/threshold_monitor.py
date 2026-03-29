from utils.rate_limiter import polygon_wait
import requests
import json
import os
from datetime import datetime
from utils.db import supabase

POLYGON_KEY = os.getenv("POLYGON_API_KEY")

# Edit these to match what matters for your thesis
THRESHOLDS = {
    "fcf_margin_drop_pp": 5.0,        # Alert if FCF margin drops 5+ percentage points vs stored baseline
    "revenue_decline_pct": 5.0,       # Alert if revenue declines 5%+ year-over-year
    "gross_margin_drop_pp": 3.0,      # Alert if gross margin drops 3+ percentage points
}


def get_latest_financials(ticker):
    """Pull most recent annual financials from Polygon."""
    url = "https://api.polygon.io/vX/reference/financials"
    params = {
        "ticker": ticker,
        "timeframe": "annual",
        "limit": 2,  # Get 2 years so we can compare
        "apiKey": POLYGON_KEY
    }
    polygon_wait()
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"  Polygon financials API returned {r.status_code}")
        return None
    results = r.json().get("results", [])
    return results if results else None


def extract_key_metrics(financial_result):
    """Pull the numbers we care about from a Polygon financials result."""
    fin = financial_result.get("financials", {})
    income = fin.get("income_statement", {})
    cashflow = fin.get("cash_flow_statement", {})
    balance = fin.get("balance_sheet", {})

    revenue = income.get("revenues", {}).get("value", 0)
    gross_profit = income.get("gross_profit", {}).get("value", 0)
    operating_cf = cashflow.get("net_cash_flow_from_operating_activities", {}).get("value", 0)
    capex = cashflow.get("net_cash_flow_from_investing_activities", {}).get("value", 0)

    fcf = operating_cf + capex  # capex is usually negative
    fcf_margin = (fcf / revenue * 100) if revenue else 0
    gross_margin = (gross_profit / revenue * 100) if revenue else 0

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "operating_cf": operating_cf,
        "capex": capex,
        "fcf": fcf,
        "fcf_margin": fcf_margin,
        "period": financial_result.get("end_date", "")
    }


def create_alert(company_id, alert_type, message):
    """Write an alert to the database."""
    supabase.table("alerts").insert({
        "company_id": company_id,
        "alert_type": alert_type,
        "message": message
    }).execute()
    print(f"  ⚠️  ALERT: {message[:100]}")


def update_baseline(ticker, metrics):
    """Store current metrics as the new baseline for future comparisons."""
    existing = supabase.table("baselines").select("id").eq("ticker", ticker).execute()
    if existing.data:
        supabase.table("baselines").update({
            "fcf_margin": metrics["fcf_margin"],
            "revenue": int(metrics["revenue"]),
            "updated_at": datetime.now().isoformat()
        }).eq("ticker", ticker).execute()
    else:
        supabase.table("baselines").insert({
            "ticker": ticker,
            "fcf_margin": metrics["fcf_margin"],
            "revenue": int(metrics["revenue"])
        }).execute()


def check_thresholds(ticker):
    """Compare current financials to stored baseline and fire alerts if thresholds are breached."""
    result = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not result.data:
        print(f"  {ticker} not in companies table")
        return []
    company_id = result.data[0]["id"]

    financials = get_latest_financials(ticker)
    if not financials or len(financials) == 0:
        print(f"  No financial data available")
        return []

    current_metrics = extract_key_metrics(financials[0])
    alerts_fired = []

    # Get stored baseline
    baseline_result = supabase.table("baselines").select("*").eq("ticker", ticker).execute()

    if not baseline_result.data:
        # No baseline yet — store current as baseline and exit
        print(f"  No baseline found — storing current metrics as baseline")
        update_baseline(ticker, current_metrics)
        return []

    baseline = baseline_result.data[0]

    # --- FCF Margin Check ---
    stored_fcf_margin = baseline.get("fcf_margin", 0)
    current_fcf_margin = current_metrics["fcf_margin"]
    fcf_drop = stored_fcf_margin - current_fcf_margin

    if fcf_drop > THRESHOLDS["fcf_margin_drop_pp"]:
        msg = (f"FCF margin dropped {fcf_drop:.1f}pp "
               f"(was {stored_fcf_margin:.1f}%, now {current_fcf_margin:.1f}%)")
        create_alert(company_id, "fcf_margin_drop", msg)
        alerts_fired.append(msg)

    # --- Revenue Check ---
    stored_revenue = baseline.get("revenue", 0)
    current_revenue = current_metrics["revenue"]
    if stored_revenue > 0:
        rev_change_pct = ((current_revenue - stored_revenue) / stored_revenue) * 100
        if rev_change_pct < -THRESHOLDS["revenue_decline_pct"]:
            msg = (f"Revenue declined {abs(rev_change_pct):.1f}% "
                   f"(was ${stored_revenue:,.0f}, now ${current_revenue:,.0f})")
            create_alert(company_id, "revenue_decline", msg)
            alerts_fired.append(msg)

    # Update baseline with latest data
    update_baseline(ticker, current_metrics)

    return alerts_fired


def print_financial_summary(ticker, metrics):
    """Print a clean summary of key metrics to the console."""
    print(f"  Revenue:     ${metrics['revenue']:>15,.0f}")
    print(f"  FCF:         ${metrics['fcf']:>15,.0f}  ({metrics['fcf_margin']:.1f}% margin)")
    print(f"  Gross Margin: {metrics['gross_margin']:.1f}%")
    print(f"  Period:      {metrics['period']}")


def run_threshold_monitor(tickers):
    """Main entry point — check thresholds for all watchlist tickers."""
    print(f"\n{'='*50}")
    print(f"Threshold Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    total_alerts = 0
    for ticker in tickers:
        print(f"\n📊 {ticker}")
        financials = get_latest_financials(ticker)

        if financials:
            metrics = extract_key_metrics(financials[0])
            print_financial_summary(ticker, metrics)

        alerts = check_thresholds(ticker)
        total_alerts += len(alerts)

        if not alerts:
            print(f"  ✅ All thresholds within range")

    print(f"\n{'='*50}")
    print(f"Done. {total_alerts} alert(s) fired.")


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_threshold_monitor(WATCHLIST)