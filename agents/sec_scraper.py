from utils.rate_limiter import polygon_wait
import requests
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from utils.db import supabase
from utils.ai import client

HEADERS = {"User-Agent": "YourName yourname@email.com"}  # SEC requires this
POLYGON_KEY = os.getenv("POLYGON_API_KEY")


def get_cik_for_ticker(ticker):
    """Look up a company's CIK number from SEC EDGAR."""
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=HEADERS)
    data = r.json()
    for entry in data.values():
        if entry["ticker"].upper() == ticker.upper():
            # CIK must be zero-padded to 10 digits
            return str(entry["cik_str"]).zfill(10)
    return None


def get_recent_filings(cik, form_type="8-K", days_back=7):
    """Fetch recent filings for a company from EDGAR."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"  Could not fetch filings for CIK {cik}")
        return []

    data = r.json()
    filings = data.get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    descriptions = filings.get("primaryDocument", [])

    cutoff = datetime.now() - timedelta(days=days_back)
    results = []

    for i, form in enumerate(forms):
        if form == form_type:
            filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
            if filing_date >= cutoff:
                accession_clean = accessions[i].replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{accession_clean}/{descriptions[i]}"
                )
                results.append({
                    "form": form,
                    "date": dates[i],
                    "url": doc_url,
                    "accession": accessions[i]
                })
    return results


def fetch_filing_text(url):
    """Download and return the text content of a filing."""
    polygon_wait()
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 200:
        # Strip HTML tags roughly
        import re
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:15000]  # Cap for AI context window
    return ""


def analyse_filing_with_ai(content, doc_type, ticker):
    """Send filing content to GPT and get structured analysis back."""
    prompt = f"""
You are a senior equity analyst reviewing a {doc_type} filing for {ticker}.
Analyse the following content and return a valid JSON object with these exact fields:
- summary: string, 2-3 sentence executive summary
- key_metrics: object with any numerical metrics mentioned (revenue, margins, guidance, etc.)
- sentiment_score: float from -1.0 (very negative) to 1.0 (very positive)
- thesis_tags: array of relevant investment themes (e.g. "margin_expansion", "management_change", "guidance_cut")
- flags: array of red flags or significant risks mentioned (empty array if none)

Filing content:
{content}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_document_and_analysis(ticker, doc_type, title, content, url, analysis):
    """Write document and its analysis to Supabase."""
    # Get the company's ID
    result = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not result.data:
        print(f"  {ticker} not found in companies table. Add it first.")
        return
    company_id = result.data[0]["id"]

    # Store the raw document
    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": doc_type,
        "title": title,
        "content": content,
        "source_url": url,
        "published_at": datetime.now().isoformat()
    }).execute()

    document_id = doc.data[0]["id"]

    # Store the AI analysis
    supabase.table("analysis").insert({
        "document_id": document_id,
        "summary": analysis.get("summary", ""),
        "key_metrics": analysis.get("key_metrics", {}),
        "sentiment_score": analysis.get("sentiment_score", 0),
        "thesis_tags": analysis.get("thesis_tags", []),
        "flags": analysis.get("flags", [])
    }).execute()

    # If there are flags, create an alert
    if analysis.get("flags"):
        flag_text = "; ".join(analysis["flags"][:3])
        supabase.table("alerts").insert({
            "company_id": company_id,
            "alert_type": "filing_flag",
            "message": f"{doc_type} red flag: {flag_text}"
        }).execute()
        print(f"  ⚠️  Alert created: {flag_text[:80]}")


def run_sec_scraper(tickers, form_types=["8-K", "10-Q"], days_back=7):
    """Main entry point — run for all your watchlist tickers."""
    print(f"\n{'='*50}")
    print(f"SEC EDGAR Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Scanning {len(tickers)} tickers for {form_types}")
    print(f"{'='*50}")

    for ticker in tickers:
        print(f"\n📄 {ticker}")
        cik = get_cik_for_ticker(ticker)
        if not cik:
            print(f"  Could not find CIK for {ticker}")
            continue

        for form_type in form_types:
            filings = get_recent_filings(cik, form_type, days_back)
            if not filings:
                print(f"  No new {form_type} filings in last {days_back} days")
                continue

            for filing in filings:
                print(f"  Found {form_type} filed {filing['date']} — fetching...")
                content = fetch_filing_text(filing["url"])

                if not content or len(content) < 200:
                    print(f"  Could not extract content, skipping")
                    continue

                print(f"  Analysing with AI...")
                analysis = analyse_filing_with_ai(content, form_type, ticker)
                store_document_and_analysis(
                    ticker, form_type,
                    f"{form_type} — {filing['date']}",
                    content, filing["url"], analysis
                )
                print(f"  ✅ Stored. Sentiment: {analysis.get('sentiment_score', 0):.2f}")
                if analysis.get("thesis_tags"):
                    print(f"  Tags: {', '.join(analysis['thesis_tags'])}")


if __name__ == "__main__":
    # Edit this list to match your watchlist
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_sec_scraper(WATCHLIST, form_types=["8-K", "10-Q"], days_back=7)