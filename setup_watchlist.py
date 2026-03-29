from utils.db import supabase

COMPANIES = [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology"},
    {"ticker": "META", "name": "Meta Platforms", "sector": "Technology"},
]

for company in COMPANIES:
    result = supabase.table("companies").upsert(company, on_conflict="ticker").execute()
    print(f"Added {company['ticker']} — {company['name']}")

print("\nWatchlist setup complete.")