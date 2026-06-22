# DRAFT v2 — addresses the REAL root cause your last run revealed.
#
# Your run showed this is NOT "some shows lack a links page" — it's
# straightforward rate limiting. 150 sequential calls (100 links + 50
# setlists) at SLEEP_S=0.2s between calls is too fast for kglw.net's
# limiter. The first ~38 failures even showed the OLD generic error
# message, meaning api_get() wasn't fully replaced yet when this ran —
# worth double-checking the previous patch actually landed everywhere,
# since real HTTP 429s only started showing up partway through.
#
# This version:
#   1. Bumps SLEEP_S from 0.2 to 1.0 (5x slower, much less likely to
#      trip the limiter in the first place)
#   2. Adds automatic retry-with-backoff specifically on HTTP 429 —
#      waits, then retries the same request up to 3 times before
#      giving up and returning None
#   3. Keeps the detailed status/body logging from the last fix
#
# Result: the run will take longer (150 calls * ~1-2s average instead
# of *0.2s), but should actually succeed instead of failing every
# single link/setlist fetch. show_links: 0 ingested and
# setlist_songs: 0 ingested are the real problem to fix — not a
# logging cosmetic issue.
#
# Replace BOTH the SLEEP_S constant near the top of the file AND the
# api_get() function with the versions below.

import json
import time
import urllib.error
import urllib.request
from typing import Any

# Was: SLEEP_S = 0.2
# 150 sequential calls at 0.2s apart finished fast enough to trip
# kglw.net's rate limiter partway through. 1.0s is a more conservative
# starting point — adjust further if 429s still appear.
SLEEP_S = 1.0

MAX_RETRIES = 3
RETRY_BACKOFF_S = 5.0  # wait 5s, 10s, 15s on successive 429 retries


def api_get(endpoint: str, params: dict | None = None) -> Any:
    """
    Fetch from kglw.net API. Returns parsed JSON or None on error.

    On HTTP 429 (rate limited), waits and retries up to MAX_RETRIES
    times with increasing backoff before giving up. On any other
    failure, logs the real HTTP status + a body snippet and returns
    None immediately (no retry — a 404 won't become a 200 by waiting).
    """
    url = f"{API_BASE}/{endpoint}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ons-2026/1.0 (personal use)"}
    )

    for attempt in range(1, MAX_RETRIES + 1):
        raw_body = ""
        status = None
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                status = r.status
                raw_body = r.read().decode("utf-8", errors="replace")
                return json.loads(raw_body)

        except urllib.error.HTTPError as e:
            status = e.code
            try:
                raw_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                raw_body = "<could not read error body>"

            if status == 429:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_S * attempt
                    print(f"  ⏳ rate limited on {endpoint} — waiting {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  ⚠️  API error {endpoint}: HTTP 429 — gave up after {MAX_RETRIES} attempts")
                    return None

            snippet = raw_body[:200].replace("\n", " ")
            print(f"  ⚠️  API error {endpoint}: HTTP {status} — body: {snippet!r}")
            return None

        except urllib.error.URLError as e:
            print(f"  ⚠️  API error {endpoint}: connection failed — {e.reason}")
            return None

        except json.JSONDecodeError:
            if not raw_body.strip():
                print(f"  ⚠️  API error {endpoint}: HTTP {status} but empty body")
            else:
                snippet = raw_body[:200].replace("\n", " ")
                print(f"  ⚠️  API error {endpoint}: HTTP {status}, non-JSON body: {snippet!r}")
            return None

        except Exception as e:
            print(f"  ⚠️  API error {endpoint}: unexpected — {repr(e)}")
            return None

    return None
