from scrapers.executive_tracker import run_executive_tracker
from scrapers.patent_tracker import run_patent_tracker
from scrapers.competitor_monitor import run_competitor_monitor

WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

print("🚀 Starting Phase 4 — Competitive Intelligence\n")

print("--- [1/3] Executive Movement Tracker ---")
run_executive_tracker(WATCHLIST, days_back=30)

print("\n--- [2/3] Patent Filing Monitor ---")
run_patent_tracker(WATCHLIST, months_back=6)

print("\n--- [3/3] Competitor Pricing Monitor ---")
run_competitor_monitor(WATCHLIST)

print("\n✅ Phase 4 complete.")