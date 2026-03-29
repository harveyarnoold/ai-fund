import requests
import json
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from utils.db import supabase
from utils.ai import client

load_dotenv()

# Map tickers to the exact company name USPTO uses
COMPANY_USPTO_NAMES = {
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Technology Licensing",
    "NVDA": "NVIDIA Corporation",
    "GOOGL": "Google LLC",
    "META": "Meta Platforms",
}


def get_recent_patents(company_name, months_back=6):
    """Query USPTO PatentsView API for recent patent filings."""
    start_date = (date.today() - timedelta(days=months_back * 30)).isoformat()

    url = "https://api.patentsview.org/patents/query"
    query = {
        "q": {
            "_and": [
                {"_contains": {"assignee_organization": company_name}},
                {"_gte": {"patent_date": start_date}}
            ]
        },
        "f": [
            "patent_title",
            "patent_abstract",
            "patent_date",
            "patent_number",
            "cpc_category",
            "cpc_subgroup_id"
        ],
        "o": {"per_page": 100, "sort": [{"patent_date": "desc"}]}
    }

    try:
        r = requests.post(url, json=query, timeout=30)
        if r.status_code == 200:
            return r.json().get("patents", [])
        else:
            print(f"  PatentsView returned {r.status_code}")
            return []
    except Exception as e:
        print(f"  Patent API error: {e}")
        return []


def analyse_patent_strategy(ticker, company_name, patents):
    """Use AI to identify R&D direction from patent filings."""
    if not patents:
        return None

    # Format patents for the prompt
    patent_summaries = []
    for p in patents[:25]:
        patent_summaries.append(
            f"Title: {p.get('patent_title', '')}\n"
            f"Date: {p.get('patent_date', '')}\n"
            f"Abstract: {str(p.get('patent_abstract', ''))[:300]}\n"
            f"Category: {p.get('cpc_category', '')}"
        )

    patents_text = "\n---\n".join(patent_summaries)

    prompt = f"""
You are an investment analyst reviewing patent filings for {company_name} ({ticker}).
Analyse these {len(patents)} recent patents (last 6 months) to identify R&D strategy.

{patents_text}

Return a JSON object with:
- technology_themes: array of the main technology areas being patented (max 6)
- emerging_bets: array of new areas that suggest strategic pivots or new product bets
- defensive_moats: array of areas where they appear to be defensively protecting existing business
- strategic_intent: "offensive_expansion" | "defensive_moat" | "mixed" | "maintenance"
- investment_implication: 2-3 sentences on what this patent activity means for investors
- time_horizon_years: integer, estimated years before these R&D bets show in earnings (1-5)
- confidence: "low" | "medium" | "high"
- top_insight: the single most interesting signal from the patent data (1 sentence)
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_patent_analysis(ticker, patents, analysis):
    """Store patent analysis in Supabase."""
    company = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not company.data:
        return
    company_id = company.data[0]["id"]

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "patent_analysis",
        "title": f"Patent Filing Analysis — {datetime.now().strftime('%Y-%m-%d')}",
        "content": json.dumps({
            "patent_count": len(patents),
            "analysis": analysis
        }),
        "source_url": "https://patentsview.org",
        "published_at": datetime.now().isoformat()
    }).execute()

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis.get("investment_implication", ""),
        "key_metrics": {
            "patent_count": len(patents),
            "strategic_intent": analysis.get("strategic_intent", ""),
            "time_horizon_years": analysis.get("time_horizon_years", 0),
            "confidence": analysis.get("confidence", "low")
        },
        "sentiment_score": 0.3,
        "thesis_tags": ["patent_analysis", analysis.get("strategic_intent", "")],
        "flags": []
    }).execute()


def run_patent_tracker(tickers, months_back=6):
    """Main entry point — analyse patent filings for watchlist companies."""
    print(f"\n{'='*50}")
    print(f"Patent Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for ticker in tickers:
        company_name = COMPANY_USPTO_NAMES.get(ticker, ticker)
        print(f"\n🔬 {ticker} — {company_name}")
        print(f"  Fetching patents from USPTO (last {months_back} months)...")

        patents = get_recent_patents(company_name, months_back)

        if not patents:
            print(f"  No patents found — try a different company name spelling")
            continue

        print(f"  Found {len(patents)} patents, analysing with AI...")
        analysis = analyse_patent_strategy(ticker, company_name, patents)

        if not analysis:
            print(f"  Analysis failed")
            continue

        print(f"  Strategic Intent: {analysis.get('strategic_intent', 'N/A')}")
        print(f"  Time Horizon:     {analysis.get('time_horizon_years', 'N/A')} years to earnings impact")
        print(f"  Top Insight:      {analysis.get('top_insight', 'N/A')}")
        print(f"  Tech Themes:")
        for theme in analysis.get("technology_themes", [])[:5]:
            print(f"    → {theme}")
        print(f"  Implication: {analysis.get('investment_implication', 'N/A')}")

        store_patent_analysis(ticker, patents, analysis)
        print(f"  ✅ Stored")


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_patent_tracker(WATCHLIST, months_back=6)