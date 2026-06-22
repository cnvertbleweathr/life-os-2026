# DRAFT — NOT TESTED, needs your .venv to verify against the real
# kglw.net API responses for the 7 failing show IDs.
#
# Problem: api_get() in pipelines/kglw_pipeline.py catches every failure
# mode (network error, HTTP error status, empty body, malformed JSON)
# under one generic `except Exception as e: print(f"API error: {e}")`.
# When json.loads() gets an empty string, the exception message is just
# "Expecting value: line 1 column 1 (char 0)" — which tells you JSON
# parsing failed, but nothing about WHY (404? 500? empty 200? rate limit?).
#
# This rewrite separates "got a response, but it wasn't JSON" from
# "request itself failed," and logs the actual HTTP status + a snippet
# of the raw body in the first case. Once you re-run with this, the
# next log for those 7 show IDs will say something like:
#   "API error links/show/1781483739: HTTP 404 — body: 'Not Found'"
# or
#   "API error links/show/1781483739: HTTP 200 but empty body"
# instead of just the opaque JSONDecodeError.
#
# Drop-in replacement for the existing api_get() function — same
# signature, same call sites, no changes needed anywhere else in the file.

import json
import urllib.error
import urllib.request
from typing import Any


def api_get(endpoint: str, params: dict | None = None) -> Any:
    """
    Fetch from kglw.net API. Returns parsed JSON or None on error.

    On failure, prints the actual HTTP status code and a snippet of the
    raw response body (not just the downstream JSON-decode exception),
    so "404 - this show has no links page" is distinguishable from
    "500 - something's actually broken" or "200 but truly empty body."
    """
    url = f"{API_BASE}/{endpoint}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ons-2026/1.0 (personal use)"}
    )

    raw_body = ""
    status = None
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            raw_body = r.read().decode("utf-8", errors="replace")
            return json.loads(raw_body)
    except urllib.error.HTTPError as e:
        # Server responded with a 4xx/5xx - this is the case that was
        # previously indistinguishable from "empty 200 body."
        status = e.code
        try:
            raw_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw_body = "<could not read error body>"
        snippet = raw_body[:200].replace("\n", " ")
        print(f"  WARNING api error {endpoint}: HTTP {status} - body: {snippet!r}")
        return None
    except urllib.error.URLError as e:
        # DNS failure, connection refused, timeout, etc. - the request
        # itself never completed, no status code to report.
        print(f"  WARNING api error {endpoint}: connection failed - {e.reason}")
        return None
    except json.JSONDecodeError:
        # Got a response (status is set), but the body wasn't valid JSON.
        # Most likely an empty 200, or an HTML page where JSON was expected.
        if not raw_body.strip():
            print(f"  WARNING api error {endpoint}: HTTP {status} but empty body")
        else:
            snippet = raw_body[:200].replace("\n", " ")
            print(f"  WARNING api error {endpoint}: HTTP {status}, non-JSON body: {snippet!r}")
        return None
    except Exception as e:
        # Genuinely unexpected - keep the original catch-all so nothing
        # new can crash the pipeline, but label it clearly as unexpected
        # rather than lumping it in with the well-understood cases above.
        print(f"  WARNING api error {endpoint}: unexpected - {repr(e)}")
        return None
