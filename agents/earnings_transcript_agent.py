import requests
import json
import os
from datetime import datetime
from utils.db import supabase
from utils.ai import client

POLYGON_KEY = os.getenv("POLYGON_API_KEY")


def get_earnings_transcripts(ticker, limit=4):
    """Fetch earnings call transcripts from Polygon.io."""
    url = "https://api.polygon.io/vX/reference/earnings-call-transcripts"
    params = {"ticker": ticker, "limit": limit, "apiKey": POLYGON_KEY}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"  Polygon transcript API returned {r.status_code}")
        return []
    return r.json().get("results", [])


def extract_transcript_text(transcript_obj):
    """Pull the full text from a transcript result object."""
    # Polygon returns transcript in 'transcript' field as a list of speaker segments
    segments = transcript_obj.get("transcript", [])
    if isinstance(segments, list):
        return " ".join([seg.get("text", "") for seg in segments])
    elif isinstance(segments, str):
        return segments
    return ""


def analyse_transcript(text, ticker, quarter):
    """Ask AI to extract key signals from an earnings call transcript."""
    prompt = f"""
You are a senior equity analyst reviewing the {quarter} earnings call transcript for {ticker}.

Extract the following and return as a JSON object:
- summary: 3-4 sentence summary of the call
- guidance_commentary: what management said about forward guidance (be specific with numbers if mentioned)
- key_metrics: object with revenue, EPS, margins, or any other numbers stated
- management_tone: "confident" | "cautious" | "defensive" | "mixed"
- bullish_signals: array of positive developments mentioned
- bearish_signals: array of concerns, risks, or negatives mentioned
- sentiment_score: float from -1.0 to 1.0
- flags: array of red flags (empty if none)
- thesis_tags: array of investment themes

Transcript:
{text[:10000]}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def compare_transcripts(current_text, previous_text, ticker):
    """Detect language and tone shifts between two consecutive earnings calls."""
    prompt = f"""
Compare these two {ticker} earnings call transcripts (current quarter vs previous quarter).

Identify and return as JSON:
- tone_shift: did management become more or less confident? (specific examples)
- new_topics: topics or themes that appeared this quarter but not last
- dropped_topics: topics discussed last quarter that disappeared this quarter
- guidance_change: any changes in forward guidance language or numbers
- key_language_changes: array of specific phrase changes worth noting (e.g. "changed 'strong growth' to 'moderate growth'")
- overall_signal: "more bullish" | "more bearish" | "neutral" with a one sentence reason

CURRENT QUARTER:
{current_text[:5000]}

PREVIOUS QUARTER:
{previous_text[:5000]}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def store_transcript_analysis(ticker, quarter, text, analysis, url=""):
    """Store transcript and analysis in Supabase."""
    result = supabase.table("companies").select("id").eq("ticker", ticker).execute()
    if not result.data:
        print(f"  {ticker} not in companies table")
        return
    company_id = result.data[0]["id"]

    doc = supabase.table("documents").insert({
        "company_id": company_id,
        "doc_type": "earnings_transcript",
        "title": f"Earnings Call — {quarter}",
        "content": text[:50000],
        "source_url": url,
        "published_at": datetime.now().isoformat()
    }).execute()

    supabase.table("analysis").insert({
        "document_id": doc.data[0]["id"],
        "summary": analysis.get("summary", ""),
        "key_metrics": analysis.get("key_metrics", {}),
        "sentiment_score": analysis.get("sentiment_score", 0),
        "thesis_tags": analysis.get("thesis_tags", []),
        "flags": analysis.get("flags", [])
    }).execute()


def run_transcript_agent(tickers):
    """Main entry point — fetch, analyse, and compare transcripts for watchlist."""
    print(f"\n{'='*50}")
    print(f"Earnings Transcript Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for ticker in tickers:
        print(f"\n🎙️  {ticker}")
        transcripts = get_earnings_transcripts(ticker, limit=4)

        if not transcripts:
            print(f"  No transcripts available (Polygon free tier may not include this)")
            continue

        # Analyse the most recent transcript
        latest = transcripts[0]
        quarter = latest.get("period_of_report", "Unknown Quarter")
        text = extract_transcript_text(latest)

        if not text:
            print(f"  Could not extract transcript text")
            continue

        print(f"  Analysing {quarter} transcript...")
        analysis = analyse_transcript(text, ticker, quarter)
        store_transcript_analysis(ticker, quarter, text, analysis)

        print(f"  ✅ Stored. Tone: {analysis.get('management_tone')} | Sentiment: {analysis.get('sentiment_score', 0):.2f}")

        # If we have 2+ transcripts, do a comparison
        if len(transcripts) >= 2:
            print(f"  Comparing to previous quarter...")
            prev_text = extract_transcript_text(transcripts[1])
            if prev_text:
                comparison = compare_transcripts(text, prev_text, ticker)
                print(f"  Overall signal: {comparison.get('overall_signal', 'N/A')}")
                if comparison.get("key_language_changes"):
                    for change in comparison["key_language_changes"][:3]:
                        print(f"    → {change}")


if __name__ == "__main__":
    WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
    run_transcript_agent(WATCHLIST)