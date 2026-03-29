from scrapers.web_traffic_tracker import run_web_traffic_agent

WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

APP_NAMES = {
    "AAPL": "apple music",
    "MSFT": "microsoft teams",
    "NVDA": None,
    "GOOGL": "google maps",
    "META": "instagram",
}

print("🚀 Starting Phase 3 — App Store Intelligence\n")

run_web_traffic_agent(WATCHLIST, APP_NAMES)

print("\n✅ Phase 3 complete.")