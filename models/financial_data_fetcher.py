from utils.rate_limiter import polygon_wait
import requests
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

POLYGON_KEY = os.getenv("POLYGON_API_KEY")


def get_financials(ticker, limit=5):
    """Pull up to 5 years of annual financials from Polygon."""
    url = "https://api.polygon.io/vX/reference/financials"
    params = {
        "ticker": ticker,
        "timeframe": "annual",
        "limit": limit,
        "order": "desc",
        "apiKey": POLYGON_KEY
    }
    polygon_wait()
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"  Polygon returned {r.status_code} for {ticker}")
        return None

    results = r.json().get("results", [])
    if not results:
        print(f"  No financial data found for {ticker}")
        return None

    income_rows = []
    cashflow_rows = []
    balance_rows = []

    for period in results:
        date = period.get("end_date", "")
        fin = period.get("financials", {})

        inc = fin.get("income_statement", {})
        cf = fin.get("cash_flow_statement", {})
        bal = fin.get("balance_sheet", {})

        revenue = inc.get("revenues", {}).get("value", 0) or 0
        gross_profit = inc.get("gross_profit", {}).get("value", 0) or 0
        operating_income = inc.get("operating_income_loss", {}).get("value", 0) or 0
        net_income = inc.get("net_income_loss", {}).get("value", 0) or 0

        operating_cf = cf.get("net_cash_flow_from_operating_activities", {}).get("value", 0) or 0
        investing_cf = cf.get("net_cash_flow_from_investing_activities", {}).get("value", 0) or 0
        capex = investing_cf  # Investing CF is mostly capex
        fcf = operating_cf + capex  # capex is negative, so this subtracts

        cash = bal.get("cash", {}).get("value", 0) or 0
        total_debt = bal.get("long_term_debt", {}).get("value", 0) or 0

        income_rows.append({
            "date": date,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "gross_margin": (gross_profit / revenue * 100) if revenue else 0,
            "operating_income": operating_income,
            "operating_margin": (operating_income / revenue * 100) if revenue else 0,
            "net_income": net_income,
            "net_margin": (net_income / revenue * 100) if revenue else 0,
        })

        cashflow_rows.append({
            "date": date,
            "operating_cf": operating_cf,
            "capex": capex,
            "fcf": fcf,
            "fcf_margin": (fcf / revenue * 100) if revenue else 0,
        })

        balance_rows.append({
            "date": date,
            "cash": cash,
            "total_debt": total_debt,
            "net_cash": cash - total_debt,
        })

    income_df = pd.DataFrame(income_rows).set_index("date").sort_index()
    cashflow_df = pd.DataFrame(cashflow_rows).set_index("date").sort_index()
    balance_df = pd.DataFrame(balance_rows).set_index("date").sort_index()

    return {
        "income": income_df,
        "cashflow": cashflow_df,
        "balance": balance_df,
        "raw": results
    }


def calculate_historical_metrics(financials):
    """Derive the key historical metrics we feed into the DCF assumptions."""
    inc = financials["income"]
    cf = financials["cashflow"]
    bal = financials["balance"]

    metrics = {}

    # Revenue growth
    if len(inc) >= 2:
        rev_values = inc["revenue"].values
        growth_rates = []
        for i in range(1, len(rev_values)):
            if rev_values[i-1] and rev_values[i-1] != 0:
                growth_rates.append((rev_values[i] - rev_values[i-1]) / abs(rev_values[i-1]) * 100)
        metrics["avg_revenue_growth"] = sum(growth_rates) / len(growth_rates) if growth_rates else 0
        metrics["last_revenue_growth"] = growth_rates[-1] if growth_rates else 0
    else:
        metrics["avg_revenue_growth"] = 0
        metrics["last_revenue_growth"] = 0

    # Margins (average over available years)
    metrics["avg_gross_margin"] = inc["gross_margin"].mean()
    metrics["avg_operating_margin"] = inc["operating_margin"].mean()
    metrics["avg_net_margin"] = inc["net_margin"].mean()
    metrics["avg_fcf_margin"] = cf["fcf_margin"].mean()

    # Most recent year values
    metrics["last_revenue"] = inc["revenue"].iloc[-1]
    metrics["last_fcf"] = cf["fcf"].iloc[-1]
    metrics["last_fcf_margin"] = cf["fcf_margin"].iloc[-1]
    metrics["last_net_cash"] = bal["net_cash"].iloc[-1]

    return metrics


def print_financial_summary(ticker, financials, metrics):
    """Print a clean table of the key financials."""
    print(f"\n  {'Year':<12} {'Revenue':>14} {'Gross Mgn':>10} {'FCF':>14} {'FCF Mgn':>10}")
    print(f"  {'-'*62}")

    inc = financials["income"]
    cf = financials["cashflow"]

    for date in inc.index:
        rev = inc.loc[date, "revenue"]
        gm = inc.loc[date, "gross_margin"]
        fcf = cf.loc[date, "fcf"] if date in cf.index else 0
        fcf_m = cf.loc[date, "fcf_margin"] if date in cf.index else 0
        print(f"  {date:<12} ${rev:>13,.0f} {gm:>9.1f}% ${fcf:>13,.0f} {fcf_m:>9.1f}%")

    print(f"\n  Avg Revenue Growth: {metrics['avg_revenue_growth']:.1f}%")
    print(f"  Avg FCF Margin:     {metrics['avg_fcf_margin']:.1f}%")
    print(f"  Net Cash Position:  ${metrics['last_net_cash']:,.0f}")