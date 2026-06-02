"""
fetch_wod.py — Scrape today's WOD from CrossFit Park Hill using Playwright.

URL format: https://www.crossfitparkhill.com/wod/{day}-{mon}-{year}
e.g. https://www.crossfitparkhill.com/wod/1-jun-2026

Saves to: data/fitness/wod_today.json

First-time setup (run once):
    playwright install chromium --with-deps
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "fitness" / "wod_today.json"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def wod_url(d: date) -> str:
    day = str(d.day)
    mon = d.strftime("%b").lower()
    yr  = d.strftime("%Y")
    return f"https://www.crossfitparkhill.com/wod/{day}-{mon}-{yr}"


def extract_movements(text: str) -> list[str]:
    """
    Pull capitalised multi-word movement names and CF-specific acronyms.
    Excludes very short words and common non-movement caps (Sets, Reps, etc.).
    """
    skip = {"Sets", "Reps", "Rest", "Build", "Every", "Minutes", "Seconds",
            "Scores", "Score", "Part", "Total", "Max", "Min", "Written",
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday", "June", "May", "April", "March",
            "February", "January", "July", "August", "September",
            "October", "November", "December"}
    acronyms = {"AMRAP", "EMOM", "RFT", "RNFT", "WOD", "AFAP", "OTM"}

    found = []
    # Multi-word capitalised phrases (Title Case)
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
        w = m.group(1)
        if w not in skip and len(w) > 4:
            found.append(w)
    # Single capitalised words that are known movements
    for m in re.finditer(r'\b([A-Z][a-z]{3,})\b', text):
        w = m.group(1)
        if w not in skip and w not in found:
            found.append(w)
    # CF acronyms
    for a in acronyms:
        if a in text and a not in found:
            found.append(a)

    return list(dict.fromkeys(found))  # dedupe, preserve order


def scrape_wod(d: date) -> dict:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    url = wod_url(d)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Primary: og:description meta tag has full WOD text
            og_desc = page.get_attribute('meta[property="og:description"]', "content") or ""

            # Fallback: grab the article body text
            body_text = ""
            if not og_desc:
                try:
                    article = page.locator("article").first
                    body_text = article.inner_text(timeout=5000)
                except Exception:
                    body_text = page.inner_text("body")

            browser.close()

        raw = og_desc or body_text
        # Normalise whitespace
        wod_text = re.sub(r'[ \t]+', ' ', raw).strip()
        wod_text = re.sub(r'\n{3,}', '\n\n', wod_text)

        movements = extract_movements(wod_text)

        return {
            "date": d.isoformat(),
            "url": url,
            "text": wod_text,
            "movements": movements,
            "fetched_ok": True,
        }

    except PWTimeout:
        return {"date": d.isoformat(), "url": url, "text": "", "movements": [],
                "fetched_ok": False, "error": "Timeout loading page"}
    except Exception as e:
        return {"date": d.isoformat(), "url": url, "text": "", "movements": [],
                "fetched_ok": False, "error": str(e)}


def main():
    today = date.today()

    # Skip re-fetch if already done today
    if OUTPUT.exists():
        try:
            cached = json.loads(OUTPUT.read_text())
            if cached.get("date") == today.isoformat() and cached.get("fetched_ok"):
                print(f"WOD already fetched today ({len(cached['text'])} chars). Skipping.")
                return
        except Exception:
            pass

    print(f"Fetching WOD for {today} from Park Hill...")
    wod = scrape_wod(today)
    OUTPUT.write_text(json.dumps(wod, indent=2))

    if wod["fetched_ok"]:
        print(f"✓ WOD fetched: {len(wod['text'])} chars")
        print(f"  Movements: {wod['movements']}")
    else:
        print(f"✗ WOD fetch failed: {wod.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
