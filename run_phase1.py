from agents.sec_scraper import run_sec_scraper
from agents.earnings_transcript_agent import run_transcript_agent
from agents.news_agent import run_news_agent
from alerts.threshold_monitor import run_threshold_monitor

WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

print("🚀 Starting Phase 1 Pipeline\n")

print("--- [1/4] SEC Filings ---")
run_sec_scraper(WATCHLIST, form_types=["8-K", "10-Q"], days_back=7)

print("\n--- [2/4] Earnings Transcripts ---")
run_transcript_agent(WATCHLIST)

print("\n--- [3/4] News ---")
run_news_agent(WATCHLIST, hours_back=24)

print("\n--- [4/4] Threshold Alerts ---")
run_threshold_monitor(WATCHLIST)

print("\n✅ Phase 1 complete.")