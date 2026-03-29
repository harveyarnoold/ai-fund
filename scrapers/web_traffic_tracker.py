import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from utils.db import supabase
from utils.ai import client

load_dotenv()


# Company domain map — what website to track for each ticker
COMPANY_DOMAINS = {
    "AAPL": "apple.com",
    "MSFT": "microsoft.com",
    "NVDA": "nvidia.com",
    "GOOGL": "google.com",
    "META": "meta.com",
}


def get_app_reviews(app_name, country="us", num_reviews=50):
    """
    Pull recent App Store reviews using app-store-scraper.
    Install with: pip install app-store-scraper
    """
    try:
        from app_store_scraper import AppStore
        app = AppStore(country=country, app_name=app_name)
        app.review(how="recent", sleep=0.5)
        return app.reviews[:num_reviews] if app.reviews else []
    except ImportError:
        print(f"  app-store-scraper not installed — run: pip install app-store-scraper")
        return []
    except Exception as e:
        print(f"  App store scrape failed: {e}")
        return []


def analyse_app_reviews(ticker, app_name, reviews):
    """Use AI to extract investment signals from app store reviews."""
    if not reviews:
        return None

    review_text = "\n".join([
        f"Rating: {r.get('rating', '?')}/5 — {str(r.get('review', ''))[:200]}"
        for r in reviews[:30]
    ])

    prompt = f"""
You are an investment analyst reviewing recent App Store reviews for {app_name} ({ticker}).
Extract investment-relevant signals from these {len(reviews)} recent reviews.

Reviews:
{review_text}

Return a JSON object with:
- avg_rating: float, calculated average of the ratings shown
- product_health: "declining" | "stable" | "improving"
- top_complaints: array of recurring user complaints (max 5)
- top_praise: array of recurring things users love (max 5)
- churn_risk: "low" | "medium" | "high" — are users threatening to leave?
- pricing_friction: true/false — are users complaining about price increases?
- investment_signal: 1-2 sentence investment implication
- sentiment_score: float -1.0 to 1.0
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_app_analysis(ticker, app_name, analysis):
    """Store app review analysis in Supabase."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        return
    company_id = company.data[0]["id"]

    flags = []
    if analysis.get("pricing_friction"):
        flags.append("pricing_friction_detected")
    if analysis.get("churn_risk") == "high":
        flags.append("high_churn_risk")

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "app_review_analysis",
        "title": f"App Store Analysis — {app_name} — {datetime.now().strftime('%Y-%m-%d')}",
        "content": json.dumps(analysis),
        "source_url": f"https://apps.apple.com/search?term={app_name}",
        "published_at": datetime.now().isoformat()
    }).execute()

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis.get("investment_signal", ""),
        "key_metrics": {
            "avg_rating": analysis.get("avg_rating", 0),
            "product_health": analysis.get("product_health", "stable"),
            "churn_risk": analysis.get("churn_risk", "low"),
            "pricing_friction": analysis.get("pricing_friction", False)
        },
        "sentiment_score": analysis.get("sentiment_score", 0),
        "thesis_tags": ["app_reviews", analysis.get("product_health", "stable")],
        "flags": flags
    }).execute()

    for flag in flags:
        supabase.table("alerts").insert({
            "company_id": company_id,
            "alert_type": flag,
            "message": f"{ticker} app reviews: {flag.replace('_', ' ')} — {analysis.get('investment_signal', '')[:120]}"
        }).execute()


def run_web_traffic_agent(tickers, app_names):
    """Main entry point — analyse app store sentiment for watchlist companies."""
    print(f"\n{'='*50}")
    print(f"Web Traffic & App Review Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for ticker in tickers:
        app_name = app_names.get(ticker)
        if not app_name:
            print(f"\n🌐 {ticker} — no app name configured, skipping")
            continue

        print(f"\n🌐 {ticker} — {app_name}")
        print(f"  Scraping App Store reviews...")

        reviews = get_app_reviews(app_name, country="us", num_reviews=50)

        if not reviews:
            print(f"  No reviews retrieved")
            continue

        print(f"  Retrieved {len(reviews)} reviews, analysing with AI...")
        analysis = analyse_app_reviews(ticker, app_name, reviews)

        if not analysis:
            print(f"  Analysis failed")
            continue

        print(f"  Product Health:  {analysis.get('product_health', 'N/A')}")
        print(f"  Avg Rating:      {analysis.get('avg_rating', 'N/A')}")
        print(f"  Churn Risk:      {analysis.get('churn_risk', 'N/A')}")
        print(f"  Pricing Friction: {analysis.get('pricing_friction', False)}")
        print(f"  Signal: {analysis.get('investment_signal', 'N/A')}")

        store_app_analysis(ticker, app_name, analysis)
        print(f"  ✅ Stored")


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    APP_NAMES = {
        "AAPL": "apple music",
        "MSFT": "microsoft teams",
        "NVDA": None,           # NVDA has no consumer app — skip
        "GOOGL": "google maps",
        "META": "instagram",
    }
    run_web_traffic_agent(WATCHLIST, APP_NAMES)