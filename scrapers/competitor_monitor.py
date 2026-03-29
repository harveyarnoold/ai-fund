import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from utils.db import supabase
from utils.ai import client

load_dotenv()

# Define competitors and their pricing pages for each company you track
COMPETITOR_MAP = {
    "MSFT": {
        "Google Workspace": "https://workspace.google.com/pricing",
        "Zoom": "https://zoom.us/pricing",
        "Slack": "https://slack.com/pricing",
    },
    "META": {
        "Snapchat Ads": "https://forbusiness.snapchat.com/advertising/pricing",
        "TikTok Ads": "https://ads.tiktok.com/help/article/about-tiktok-ads-pricing",
    },
    "GOOGL": {
        "Microsoft 365": "https://www.microsoft.com/en-us/microsoft-365/business/compare-all-plans",
        "Zoom": "https://zoom.us/pricing",
    },
    "AAPL": {
        "Spotify": "https://www.spotify.com/us/premium/",
        "Samsung": "https://www.samsung.com/us/smartphones/",
    },
    "NVDA": {
        "AMD": "https://www.amd.com/en/products/graphics/desktops",
        "Intel Arc": "https://www.intel.com/content/www/us/en/products/docs/discrete-gpus/arc/desktop/a-series/overview.html",
    }
}


async def scrape_page_text(url):
    """Scrape the visible text from a webpage using Playwright."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            content = await page.inner_text("body")
            await browser.close()
            return content[:8000]
    except ImportError:
        print(f"  Playwright not installed — run: pip install playwright && playwright install chromium")
        return ""
    except Exception as e:
        print(f"  Scrape failed for {url}: {e}")
        return ""


def get_stored_content(ticker, competitor_name):
    """Retrieve previously stored pricing page content from Supabase."""
    result = supabase.table("documents").select("content, ingested_at") \
        .eq("doc_type", "competitor_pricing") \
        .like("title", f"%{competitor_name}%") \
        .order("ingested_at", desc=True) \
        .limit(1) \
        .execute()
    if result.data:
        return result.data[0]["content"]
    return None


def store_pricing_content(ticker, competitor_name, url, content):
    """Store scraped pricing content in Supabase."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        return
    company_id = company.data[0]["id"]

    supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "competitor_pricing",
        "title": f"Competitor Pricing — {competitor_name} — {datetime.now().strftime('%Y-%m-%d')}",
        "content": content,
        "source_url": url,
        "published_at": datetime.now().isoformat()
    }).execute()


def detect_pricing_changes(ticker, competitor_name, current_content, stored_content):
    """Ask AI to identify what changed between two versions of a pricing page."""
    prompt = f"""
You are a competitive intelligence analyst for {ticker}.
Compare these two versions of {competitor_name}'s pricing page.

PREVIOUS VERSION (older):
{stored_content[:3000]}

CURRENT VERSION (newer):
{current_content[:3000]}

Identify any changes and return a JSON object with:
- changes_detected: true/false
- pricing_changes: array of specific price changes (e.g. "Pro plan increased from $12 to $15/mo")
- tier_changes: array of plan restructuring or new/removed tiers
- feature_changes: array of features added or removed from plans
- competitive_impact_score: integer 1-10 (how much does this affect {ticker}?)
- investment_implication: 1-2 sentences on what this means for {ticker}
- summary: one sentence overall assessment
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_change_analysis(ticker, competitor_name, analysis):
    """Store competitor change analysis and fire alert if significant."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        return
    company_id = company.data[0]["id"]

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "competitor_change_analysis",
        "title": f"Competitor Change — {competitor_name} — {datetime.now().strftime('%Y-%m-%d')}",
        "content": json.dumps(analysis),
        "source_url": "",
        "published_at": datetime.now().isoformat()
    }).execute()

    impact = analysis.get("competitive_impact_score", 0)

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis.get("investment_implication", ""),
        "key_metrics": {
            "competitor": competitor_name,
            "impact_score": impact,
            "changes_detected": analysis.get("changes_detected", False)
        },
        "sentiment_score": -0.3 * (impact / 10),
        "thesis_tags": ["competitor_pricing", "competitive_intelligence"],
        "flags": ["competitor_price_change"] if analysis.get("pricing_changes") else []
    }).execute()

    if impact >= 7:
        supabase.table("alerts").insert({
            "company_id": company_id,
            "alert_type": "competitor_pricing_change",
            "message": f"{ticker} competitor alert — {competitor_name}: {analysis.get('summary', '')[:120]}"
        }).execute()
        print(f"  ⚠️  High impact alert created (score: {impact}/10)")


async def run_competitor_monitor_async(tickers):
    """Async version — scrapes all competitor pages."""
    print(f"\n{'='*50}")
    print(f"Competitor Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for ticker in tickers:
        competitors = COMPETITOR_MAP.get(ticker, {})
        if not competitors:
            print(f"\n🏢 {ticker} — no competitors configured")
            continue

        print(f"\n🏢 {ticker}")

        for competitor_name, url in competitors.items():
            print(f"  Checking {competitor_name}...")

            current_content = await scrape_page_text(url)
            if not current_content:
                print(f"  Could not scrape {url}")
                continue

            stored_content = get_stored_content(ticker, competitor_name)

            if not stored_content:
                # First time — just store as baseline
                store_pricing_content(ticker, competitor_name, url, current_content)
                print(f"  No baseline — stored current as baseline")
                continue

            # Compare to previous
            print(f"  Comparing to stored baseline with AI...")
            analysis = detect_pricing_changes(
                ticker, competitor_name, current_content, stored_content
            )

            if analysis.get("changes_detected"):
                print(f"  🔔 CHANGES DETECTED (impact: {analysis.get('competitive_impact_score')}/10)")
                if analysis.get("pricing_changes"):
                    for change in analysis["pricing_changes"]:
                        print(f"    → {change}")
                print(f"  Implication: {analysis.get('investment_implication', 'N/A')}")
                store_change_analysis(ticker, competitor_name, analysis)
            else:
                print(f"  No changes detected")

            # Update stored content with latest
            store_pricing_content(ticker, competitor_name, url, current_content)


def run_competitor_monitor(tickers):
    """Synchronous wrapper for the async competitor monitor."""
    asyncio.run(run_competitor_monitor_async(tickers))


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_competitor_monitor(WATCHLIST)