#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

URL = os.getenv("AEG_EVENTS_URL", "").strip()
if not URL:
    raise SystemExit("Missing AEG_EVENTS_URL in environment (.env).")

def _as_list(obj: Any) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        # common patterns
        for k in ("events", "data", "items", "results"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
    return []

def main() -> int:
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    data = r.json()

    events = _as_list(data)
    print("Top-level type:", type(data).__name__)
    if isinstance(data, dict):
        print("Top-level keys:", sorted(list(data.keys()))[:60])

    print("Events list length:", len(events))
    if not events:
        print("Could not find events list automatically.")
        print("First 1000 chars of JSON:", json.dumps(data)[:1000])
        return 1

    sample = events[0]
    if isinstance(sample, dict):
        print("\nSample event keys (first 80):", sorted(list(sample.keys()))[:80])
        # try common venue/title/date candidates
        cand_keys = [k for k in sample.keys() if any(s in k.lower() for s in ["venue", "location", "place", "title", "name", "date", "time", "start", "event"])]
        print("Candidate keys:", sorted(cand_keys)[:80])

        # print a small sample of key values for eyeballing
        print("\nSample event preview:")
        for k in sorted(cand_keys)[:25]:
            v = sample.get(k)
            if isinstance(v, (dict, list)):
                vv = f"<{type(v).__name__} len={len(v) if hasattr(v,'__len__') else ''}>"
            else:
                vv = v
            print(f"  {k}: {vv}")
    else:
        print("Sample event is not a dict; type:", type(sample).__name__)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
