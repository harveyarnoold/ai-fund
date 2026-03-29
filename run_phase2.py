import os
from models.financial_data_fetcher import (
    get_financials,
    calculate_historical_metrics,
    print_financial_summary
)
from models.dcf_generator import (
    generate_dcf_assumptions,
    run_dcf,
    get_shares_outstanding,
    get_current_price,
    print_dcf_results
)
from models.store_dcf import store_dcf_results
from utils.db import supabase

WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

# Sector map — used to give AI context for assumptions
SECTORS = {
    "AAPL": "Technology / Consumer Electronics",
    "MSFT": "Technology / Cloud Software",
    "NVDA": "Technology / Semiconductors",
    "GOOGL": "Technology / Digital Advertising",
    "META": "Technology / Social Media",
}

print("🚀 Starting Phase 2 — Financial Modelling Engine\n")

for ticker in WATCHLIST:
    print(f"\n{'='*60}")
    print(f"📊 {ticker}")
    print(f"{'='*60}")

    # 1. Fetch financials
    print("  Fetching financials from Polygon...")
    financials = get_financials(ticker, limit=5)
    if not financials:
        print(f"  Skipping {ticker} — no financial data available")
        continue

    # 2. Calculate historical metrics
    metrics = calculate_historical_metrics(financials)

    # 3. Print the financial history
    print_financial_summary(ticker, financials, metrics)

    # 4. Get current market data
    print("\n  Fetching current market data...")
    shares = get_shares_outstanding(ticker)
    current_price = get_current_price(ticker)
    print(f"  Current Price:       ${current_price:.2f}")
    print(f"  Shares Outstanding:  {shares:,.0f}")

    # 5. Generate AI assumptions
    print("\n  Generating DCF assumptions with AI...")
    sector = SECTORS.get(ticker, "Technology")
    assumptions = generate_dcf_assumptions(ticker, metrics, sector)

    # 6. Run the DCF
    net_cash = metrics.get("last_net_cash", 0)
    results = run_dcf(
        last_revenue=metrics["last_revenue"],
        shares_outstanding=shares,
        assumptions=assumptions,
        net_cash=net_cash,
        years=5
    )

    # 7. Print results
    print_dcf_results(ticker, results, current_price)

    # 8. Store in Supabase
    print("\n  Storing results...")
    store_dcf_results(ticker, metrics, assumptions, results, current_price)

print(f"\n{'='*60}")
print("✅ Phase 2 complete.")
print(f"{'='*60}")
print("\nView your DCF results in Supabase → Table Editor → dcf_models")