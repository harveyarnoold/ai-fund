import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils.db import supabase
from utils.ai import client

load_dotenv()

HEADERS = {"User-Agent": "YourName yourname@email.com"}


def search_executive_filings(ticker, days_back=30):
    """Search SEC EDGAR full-text search for executive change filings."""
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}" "chief" "officer"',
        "dateRange": "custom",
        "startdt": start_date,
        "forms": "8-K"
    }

    r = requests.get(
        "https://efts.sec.gov/LATEST/search-index",
        params=params,
        headers=HEADERS
    )

    if r.status_code != 200:
        print(f"  EDGAR search returned {r.status_code}")
        return []

    hits = r.json().get("hits", {}).get("hits", [])
    return hits


def fetch_filing_excerpt(filing_url):
    """Download a small excerpt of an 8-K filing."""
    try:
        r = requests.get(filing_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            import re
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:6000]
    except Exception as e:
        print(f"  Could not fetch filing: {e}")
    return ""


def analyse_executive_changes(ticker, filings):
    """Use AI to identify executive changes from 8-K filing text."""
    if not filings:
        return None

    filing_summaries = []
    for filing in filings[:5]:
        source = filing.get("_source", {})
        filing_date = source.get("period_of_report", "unknown date")
        file_url = source.get("file_date", "")

        # Build the filing URL from accession number
        entity_id = source.get("entity_id", "")
        accession = source.get("accession_no", "").replace("-", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{entity_id}/{accession}/"

        filing_summaries.append({
            "date": filing_date,
            "description": source.get("form_type", "8-K"),
            "url": doc_url,
            "text_preview": source.get("file_date", "")
        })

    prompt = f"""
You are an investment analyst reviewing SEC 8-K filings for {ticker} related to executive changes.

Based on these {len(filings)} recent filings metadata (dates range over last 30 days):
{json.dumps(filing_summaries, indent=2)}

Note: These are 8-K filings that matched a search for executive/officer mentions.
Based on typical 8-K patterns for executive changes, analyse what types of changes
might be occurring and their investment implications.

Return a JSON object with:
- likely_changes: array of likely executive change types based on filing frequency/dates
- investment_signal: "positive" | "neutral" | "negative" | "unclear"  
- urgency: "low" | "medium" | "high"
- rationale: 2-3 sentences on investment implications
- flags: array of concerns (empty if none)
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_executive_analysis(ticker, filings, analysis):
    """Store executive change analysis in Supabase."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        return
    company_id = company.data[0]["id"]

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "executive_changes",
        "title": f"Executive Change Monitor — {datetime.now().strftime('%Y-%m-%d')}",
        "content": json.dumps({"filing_count": len(filings), "analysis": analysis}),
        "source_url": "https://efts.sec.gov",
        "published_at": datetime.now().isoformat()
    }).execute()

    flags = analysis.get("flags", [])

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis.get("rationale", ""),
        "key_metrics": {
            "filing_count": len(filings),
            "investment_signal": analysis.get("investment_signal", "neutral"),
            "urgency": analysis.get("urgency", "low")
        },
        "sentiment_score": -0.5 if analysis.get("investment_signal") == "negative"
                           else 0.5 if analysis.get("investment_signal") == "positive"
                           else 0.0,
        "thesis_tags": ["executive_changes"],
        "flags": flags
    }).execute()

    if analysis.get("urgency") == "high":
        supabase.table("alerts").insert({
            "company_id": company_id,
            "alert_type": "executive_change",
            "message": f"{ticker} executive change detected — {analysis.get('rationale', '')[:120]}"
        }).execute()
        print(f"  ⚠️  Alert created")


def run_executive_tracker(tickers, days_back=30):
    """Main entry point — scan for executive changes across watchlist."""
    print(f"\n{'='*50}")
    print(f"Executive Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for ticker in tickers:
        print(f"\n👤 {ticker}")
        filings = search_executive_filings(ticker, days_back)

        if not filings:
            print(f"  No executive-related 8-K filings in last {days_back} days")
            continue

        print(f"  Found {len(filings)} relevant filing(s)")
        analysis = analyse_executive_changes(ticker, filings)

        if not analysis:
            print(f"  Could not analyse")
            continue

        print(f"  Signal:  {analysis.get('investment_signal', 'N/A')}")
        print(f"  Urgency: {analysis.get('urgency', 'N/A')}")
        print(f"  {analysis.get('rationale', '')[:120]}")

        store_executive_analysis(ticker, filings, analysis)
        print(f"  ✅ Stored")


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_executive_tracker(WATCHLIST, days_back=30)