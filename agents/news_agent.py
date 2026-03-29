from utils.rate_limiter import polygon_wait
import requests
import json
import os
from datetime import datetime, timedelta
from utils.db import supabase
from utils.ai import client

POLYGON_KEY = os.getenv("POLYGON_API_KEY")
NEWSAPI_KEY = os.getenv("NEWS_API_KEY")


def get_polygon_news(ticker, hours_back=24):
    """Pull news from Polygon.io filtered to a specific ticker."""
    cutoff = (datetime.now() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "ticker": ticker,
        "limit": 20,
        "order": "desc",
        "sort": "published_utc",
        "published_utc.gte": cutoff,
        "apiKey": POLYGON_KEY
    }
    r = requests.get(url, params=params)
    if r.status_code == 200:
        return r.json().get("results", [])
    return []


def get_newsapi_articles(ticker, company_name="", hours_back=24):
    """Pull broader news from NewsAPI.org."""
    query = f"{ticker} OR {company_name}" if company_name else ticker
    from_date = (datetime.now() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 20,
        "apiKey": NEWSAPI_KEY
    }
    polygon_wait()
    r = requests.get(url, params=params)
    if r.status_code == 200:
        return r.json().get("articles", [])
    return []


def triage_news_with_ai(articles, ticker):
    """Score articles for investment relevance and urgency."""
    if not articles:
        return []

    # Format articles for the prompt
    articles_text = "\n\n".join([
        f"ARTICLE {i+1}:\nTitle: {a.get('title', a.get('headline', {}).get('original', ''))}\n"
        f"Summary: {a.get('description', a.get('summary', ''))[:300]}"
        for i, a in enumerate(articles[:20])
    ])

    prompt = f"""
You are monitoring news for {ticker}. Review these articles and filter to only investment-relevant ones.

For each relevant article return:
- title: the article title
- relevance: integer 0-10 (how much does this affect the investment thesis?)
- urgency: integer 0-10 (does this require immediate attention?)
- sentiment: float -1.0 to 1.0
- category: one of "earnings" | "regulatory" | "management" | "macro" | "competitor" | "product" | "legal"
- reason: one sentence explaining why this is relevant

Return a JSON object with key "articles" containing an array.
Only include articles with relevance >= 5.
If nothing is relevant, return {{"articles": []}}.

Articles:
{articles_text}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content)
    return result.get("articles", [])


def store_news_article(ticker, title, content, url, source, analysis_item):
    """Store a triaged news article and its analysis."""
    result = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not result.data:
        return
    company_id = result.data[0]["id"]

    # Check if we already have this URL stored
    existing = supabase.table("documents").select("id").eq("source_url", url).execute()
    if existing.data:
        return  # Skip duplicates

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "news",
        "title": title,
        "content": content[:5000],
        "source_url": url,
        "published_at": datetime.now().isoformat()
    }).execute()

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis_item.get("reason", ""),
        "key_metrics": {"relevance": analysis_item.get("relevance"), "urgency": analysis_item.get("urgency")},
        "sentiment_score": analysis_item.get("sentiment", 0),
        "thesis_tags": [analysis_item.get("category", "general")],
        "flags": []
    }).execute()

    # Create an urgent alert if needed
    if analysis_item.get("urgency", 0) >= 8:
        supabase.table("alerts").insert({
            "company_id": company_id,
            "alert_type": "urgent_news",
            "message": f"[URGENT] {title[:120]}"
        }).execute()


def run_news_agent(tickers, hours_back=24):
    """Main entry point — scan news for all watchlist tickers."""
    print(f"\n{'='*50}")
    print(f"News Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    # Get company names from DB for better NewsAPI queries
    companies_result = supabase.table("companies").select("ticker, name").execute()
    company_names = {c["ticker"]: c.get("name", "") for c in companies_result.data}

    for ticker in tickers:
        print(f"\n📰 {ticker}")
        company_name = company_names.get(ticker, "")

        poly_articles = get_polygon_news(ticker, hours_back)
        news_articles = get_newsapi_articles(ticker, company_name, hours_back)
        all_articles = poly_articles + news_articles

        if not all_articles:
            print(f"  No articles found in last {hours_back}h")
            continue

        print(f"  Found {len(all_articles)} articles, triaging with AI...")
        relevant = triage_news_with_ai(all_articles, ticker)

        if not relevant:
            print(f"  No investment-relevant articles")
            continue

        print(f"  {len(relevant)} relevant articles found")
        for item in relevant:
            print(f"  → [{item.get('category','?').upper()}] relevance={item.get('relevance')}/10 urgency={item.get('urgency')}/10")
            print(f"    {item.get('title', '')[:80]}")

            # Find the matching article to get the URL
            title = item.get("title", "")
            matched = next(
                (a for a in all_articles
                 if title[:40].lower() in str(a.get("title", a.get("headline", {}).get("original", ""))).lower()),
                None
            )
            if matched:
                url = matched.get("url", matched.get("article_url", ""))
                content = matched.get("description", matched.get("summary", "")) or ""
                store_news_article(ticker, title, content, url, "combined", item)


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_news_agent(WATCHLIST, hours_back=24)