from utils.rate_limiter import polygon_wait
import json
import os
from utils.ai import client


def generate_dcf_assumptions(ticker, metrics, sector):
    """Ask GPT to generate bear/base/bull DCF assumptions based on historical data."""
    prompt = f"""
You are a senior equity analyst building a DCF model for {ticker} ({sector} sector).

HISTORICAL DATA (use this to calibrate your assumptions):
- Average annual revenue growth (last 5yr): {metrics['avg_revenue_growth']:.1f}%
- Most recent year revenue growth: {metrics['last_revenue_growth']:.1f}%
- Average FCF margin (last 5yr): {metrics['avg_fcf_margin']:.1f}%
- Most recent FCF margin: {metrics['last_fcf_margin']:.1f}%
- Average gross margin: {metrics['avg_gross_margin']:.1f}%
- Most recent annual revenue: ${metrics['last_revenue']:,.0f}
- Most recent annual FCF: ${metrics['last_fcf']:,.0f}
- Net cash position: ${metrics['last_net_cash']:,.0f}

Generate DCF assumptions for three scenarios: bear, base, bull.
For each scenario return:
- rev_growth_yr1_3: revenue growth rate for years 1-3 (float, percentage)
- rev_growth_yr4_5: revenue growth rate for years 4-5 (float, percentage)
- fcf_margin: FCF as a percentage of revenue (float, percentage)
- terminal_growth: long-term terminal growth rate (float, percentage, typically 2-3%)
- wacc: weighted average cost of capital (float, percentage, typically 7-12%)
- rationale: 2-3 sentences explaining the key assumptions for this scenario

Return ONLY a valid JSON object with keys: bear, base, bull.
Each containing the fields above.
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def run_dcf(last_revenue, shares_outstanding, assumptions, net_cash=0, years=5):
    """
    Run the DCF calculation for each scenario.
    Returns enterprise value, equity value, and implied share price.
    shares_outstanding should be in the same units as revenue (e.g. both in thousands).
    """
    results = {}

    for scenario, a in assumptions.items():
        fcfs = []
        revenue = last_revenue

        for yr in range(1, years + 1):
            growth = a["rev_growth_yr1_3"] if yr <= 3 else a["rev_growth_yr4_5"]
            revenue = revenue * (1 + growth / 100)
            fcf = revenue * (a["fcf_margin"] / 100)
            # Discount back to present value
            pv_fcf = fcf / ((1 + a["wacc"] / 100) ** yr)
            fcfs.append(pv_fcf)

        # Terminal value using Gordon Growth Model
        final_year_fcf = revenue * (a["fcf_margin"] / 100)
        terminal_value = (final_year_fcf * (1 + a["terminal_growth"] / 100)) / \
                         ((a["wacc"] - a["terminal_growth"]) / 100)
        # Discount terminal value back to present
        pv_terminal = terminal_value / ((1 + a["wacc"] / 100) ** years)

        pv_fcfs = sum(fcfs)
        enterprise_value = pv_fcfs + pv_terminal
        equity_value = enterprise_value + net_cash

        implied_price = (equity_value / shares_outstanding) if shares_outstanding else 0

        results[scenario] = {
            "pv_fcfs": pv_fcfs,
            "pv_terminal": pv_terminal,
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "implied_price": implied_price,
            "terminal_value_pct": (pv_terminal / enterprise_value * 100) if enterprise_value else 0,
            "assumptions": a
        }

    return results


def get_shares_outstanding(ticker):
    """Fetch current shares outstanding from Polygon."""
    import requests
    POLYGON_KEY = os.getenv("POLYGON_API_KEY")
    url = f"https://api.polygon.io/v3/reference/tickers/{ticker}"
    params = {"apiKey": POLYGON_KEY}
    polygon_wait()
    r = requests.get(url, params=params)
    if r.status_code == 200:
        data = r.json().get("results", {})
        return data.get("share_class_shares_outstanding", 0) or \
               data.get("weighted_shares_outstanding", 0)
    return 0


def get_current_price(ticker):
    """Fetch the current stock price from Polygon."""
    import requests
    POLYGON_KEY = os.getenv("POLYGON_API_KEY")
    url = f"https://api.polygon.io/v2/last/trade/{ticker}"
    params = {"apiKey": POLYGON_KEY}
    polygon_wait()
    r = requests.get(url, params=params)
    if r.status_code == 200:
        return r.json().get("results", {}).get("p", 0)
    return 0


def print_dcf_results(ticker, results, current_price):
    """Print a clean DCF output table."""
    print(f"\n  DCF Valuation Summary — {ticker}")
    print(f"  Current Market Price: ${current_price:.2f}")
    print(f"\n  {'Scenario':<10} {'EV':>16} {'Equity Val':>16} {'Implied Price':>14} {'Upside/Down':>12} {'WACC':>6} {'Terminal g':>10}")
    print(f"  {'-'*90}")

    for scenario, r in results.items():
        implied = r["implied_price"]
        if current_price and implied:
            upside = ((implied - current_price) / current_price) * 100
            upside_str = f"{upside:+.1f}%"
        else:
            upside_str = "N/A"

        a = r["assumptions"]
        print(
            f"  {scenario.upper():<10} "
            f"${r['enterprise_value']:>15,.0f} "
            f"${r['equity_value']:>15,.0f} "
            f"${implied:>13.2f} "
            f"{upside_str:>12} "
            f"{a['wacc']:>5.1f}% "
            f"{a['terminal_growth']:>9.1f}%"
        )

    print(f"\n  Rationales:")
    for scenario, r in results.items():
        print(f"\n  [{scenario.upper()}] {r['assumptions'].get('rationale', '')}")