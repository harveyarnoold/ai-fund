import os
import sys
import json
import smtplib
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────
WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

COMPANY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Google",
    "META": "Meta",
}

SECTORS = {
    "AAPL": "Technology / Consumer Electronics",
    "MSFT": "Technology / Cloud Software",
    "NVDA": "Technology / Semiconductors",
    "GOOGL": "Technology / Digital Advertising",
    "META": "Technology / Social Media",
}

APP_NAMES = {
    "AAPL": "apple music",
    "MSFT": "microsoft teams",
    "NVDA": None,
    "GOOGL": "google maps",
    "META": "instagram",
}

# Email config — fill these in to receive daily digest emails
EMAIL_ENABLED = True          # Set to True once you fill in the settings below
EMAIL_SENDER = "harveyarnold101010@gmail.com"
EMAIL_PASSWORD = "trohlmdqnjetnwpb"   # Use a Gmail App Password, not your real password
EMAIL_RECIPIENT = "harveyarnold101010@gmail.com"

# Which phases to run — set any to False to skip
RUN_PHASE1 = True
RUN_PHASE2 = True
RUN_PHASE3 = True
RUN_PHASE4 = True

# ─── LOGGING ──────────────────────────────────────────────
log_lines = []

def log(msg):
    """Print and store log lines for the email digest."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    log_lines.append(line)

def log_section(title):
    log("")
    log("=" * 55)
    log(f"  {title}")
    log("=" * 55)

# ─── EMAIL ────────────────────────────────────────────────
def send_digest_email(subject, body):
    """Send a summary email after the pipeline completes."""
    if not EMAIL_ENABLED:
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print("[EMAIL] Digest sent successfully")
    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")


# ─── ALERT SUMMARY ────────────────────────────────────────
def get_todays_alerts():
    """Pull all alerts created today from Supabase."""
    try:
        from utils.db import supabase
        today = datetime.now().strftime("%Y-%m-%d")
        result = supabase.table("alerts") \
            .select("*, companies(ticker, name)") \
            .gte("created_at", today) \
            .eq("is_read", False) \
            .execute()
        return result.data or []
    except Exception as e:
        log(f"Could not fetch alerts: {e}")
        return []


# ─── PHASE RUNNERS ────────────────────────────────────────
def run_phase1():
    log_section("PHASE 1 — Research Engine")
    try:
        from agents.sec_scraper import run_sec_scraper
        log("Running SEC scraper...")
        run_sec_scraper(WATCHLIST, form_types=["8-K", "10-Q"], days_back=1)
    except Exception as e:
        log(f"SEC scraper error: {e}")
        log(traceback.format_exc())

    try:
        from agents.earnings_transcript_agent import run_transcript_agent
        log("Running earnings transcript agent...")
        run_transcript_agent(WATCHLIST)
    except Exception as e:
        log(f"Transcript agent error: {e}")

    try:
        from agents.news_agent import run_news_agent
        log("Running news agent...")
        run_news_agent(WATCHLIST, hours_back=24)
    except Exception as e:
        log(f"News agent error: {e}")

    try:
        from alerts.threshold_monitor import run_threshold_monitor
        log("Running threshold monitor...")
        run_threshold_monitor(WATCHLIST)
    except Exception as e:
        log(f"Threshold monitor error: {e}")


def run_phase2():
    log_section("PHASE 2 — Financial Modelling")
    try:
        from models.financial_data_fetcher import get_financials, calculate_historical_metrics
        from models.dcf_generator import (
            generate_dcf_assumptions, run_dcf,
            get_shares_outstanding, get_current_price, print_dcf_results
        )
        from models.store_dcf import store_dcf_results

        for ticker in WATCHLIST:
            log(f"Running DCF for {ticker}...")
            try:
                financials = get_financials(ticker, limit=5)
                if not financials:
                    log(f"  No financials for {ticker}, skipping")
                    continue

                metrics = calculate_historical_metrics(financials)
                shares = get_shares_outstanding(ticker)
                current_price = get_current_price(ticker)
                sector = SECTORS.get(ticker, "Technology")
                assumptions = generate_dcf_assumptions(ticker, metrics, sector)
                net_cash = metrics.get("last_net_cash", 0)
                results = run_dcf(
                    last_revenue=metrics["last_revenue"],
                    shares_outstanding=shares,
                    assumptions=assumptions,
                    net_cash=net_cash,
                    years=5
                )
                store_dcf_results(ticker, metrics, assumptions, results, current_price)
                base_price = results.get("base", {}).get("implied_price", 0)
                upside = ((base_price - current_price) / current_price * 100) if current_price else 0
                log(f"  {ticker}: base case ${base_price:.2f} vs ${current_price:.2f} market ({upside:+.1f}%)")
            except Exception as e:
                log(f"  DCF failed for {ticker}: {e}")

    except Exception as e:
        log(f"Phase 2 error: {e}")
        log(traceback.format_exc())


def run_phase3():
    log_section("PHASE 3 — Alternative Data")
    try:
        from scrapers.web_traffic_tracker import run_web_traffic_agent
        log("Running app store review agent...")
        run_web_traffic_agent(WATCHLIST, APP_NAMES)
    except Exception as e:
        log(f"Web traffic agent error: {e}")


def run_phase4():
    log_section("PHASE 4 — Competitive Intelligence")
    try:
        from scrapers.executive_tracker import run_executive_tracker
        log("Running executive tracker...")
        run_executive_tracker(WATCHLIST, days_back=1)
    except Exception as e:
        log(f"Executive tracker error: {e}")

    try:
        from scrapers.patent_tracker import run_patent_tracker
        log("Running patent tracker...")
        run_patent_tracker(WATCHLIST, months_back=1)
    except Exception as e:
        log(f"Patent tracker error: {e}")

    try:
        from scrapers.competitor_monitor import run_competitor_monitor
        log("Running competitor monitor...")
        run_competitor_monitor(WATCHLIST)
    except Exception as e:
        log(f"Competitor monitor error: {e}")


# ─── MAIN ─────────────────────────────────────────────────
def main():
    start_time = datetime.now()
    log(f"🚀 Pipeline started — {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if RUN_PHASE1:
        run_phase1()

    if RUN_PHASE2:
        run_phase2()

    if RUN_PHASE3:
        run_phase3()

    if RUN_PHASE4:
        run_phase4()

    # Collect today's alerts for the digest
    log_section("ALERTS SUMMARY")
    alerts = get_todays_alerts()
    if alerts:
        log(f"{len(alerts)} unread alert(s) today:")
        for alert in alerts:
            ticker = alert.get("companies", {}).get("ticker", "?")
            log(f"  ⚠️  [{ticker}] {alert['alert_type']}: {alert['message'][:80]}")
    else:
        log("No alerts fired today — all clear")

    end_time = datetime.now()
    duration = (end_time - start_time).seconds
    log("")
    log(f"✅ Pipeline complete — {duration}s elapsed")

    # Build and send email digest
    if EMAIL_ENABLED:
        subject = f"AI Fund Pipeline — {datetime.now().strftime('%Y-%m-%d')} — {len(alerts)} alert(s)"
        body = "\n".join(log_lines)
        send_digest_email(subject, body)


if __name__ == "__main__":
    main()