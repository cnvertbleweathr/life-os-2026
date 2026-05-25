#!/usr/bin/env python3
"""
fetch_streams.py — Fetch today's sports streams from streamed.pk API.

Saves to data/streams/today.json with:
  - my_teams: matches involving your favorite teams (with stream links)
  - top5: top 5 nationally prominent matches today
  - popular: all other popular matches today

Usage:
  python scripts/fetch_streams.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "streams" / "today.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

API_BASE = "https://streamed.pk/api"
WATCH_BASE = "https://streamed.pk/watch"

MY_TEAMS = [
    "orlando magic",
    "tampa bay buccaneers",
    "orlando city",
    "miami marlins",
    "florida panthers",
    "colorado avalanche",
    "denver nuggets",
    "colorado rockies",
]

GOLF_CATEGORIES = {"golf"}

TEAM_LABELS = {
    "orlando magic":        "🏀 Orlando Magic",
    "orlando city":         "⚽ Orlando City",
    "tampa bay buccaneers": "🏈 Tampa Bay Buccaneers",
    "miami marlins":        "⚾ Miami Marlins",
    "florida panthers":     "🏒 Florida Panthers",
    "colorado avalanche":   "🏒 Colorado Avalanche",
    "denver nuggets":       "🏀 Denver Nuggets",
    "colorado rockies":     "⚾ Colorado Rockies",
}


def fetch_json(url: str, timeout: int = 15) -> list | dict | None:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "life-os/1.0"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  Warning: fetch failed for {url}: {e}")
        return None


def get_stream_url(match: dict) -> str:
    return f"{WATCH_BASE}/{match['id']}"


def normalize_match(match: dict) -> dict:
    home = (match.get("teams") or {}).get("home") or {}
    away = (match.get("teams") or {}).get("away") or {}
    ts_ms = match.get("date", 0)
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else None

    return {
        "id": match.get("id", ""),
        "title": match.get("title", ""),
        "category": match.get("category", ""),
        "popular": match.get("popular", False),
        "home_team": home.get("name", ""),
        "away_team": away.get("name", ""),
        "kickoff_utc": dt.isoformat() if dt else None,
        "kickoff_local": dt.astimezone().strftime("%I:%M %p") if dt else None,
        "watch_url": get_stream_url(match),
        "sources": match.get("sources", []),
    }


def is_my_team(match: dict) -> tuple[bool, str]:
    title = match.get("title", "").lower()
    home = (match.get("teams") or {}).get("home", {}) or {}
    away = (match.get("teams") or {}).get("away", {}) or {}
    home_name = home.get("name", "").lower()
    away_name = away.get("name", "").lower()
    category = match.get("category", "").lower()

    if category in GOLF_CATEGORIES:
        return True, "⛳ Golf"

    for team in MY_TEAMS:
        if team in title or team in home_name or team in away_name:
            label = TEAM_LABELS.get(team, team.title())
            return True, label

    return False, ""


def dedup(matches: list[dict]) -> list[dict]:
    """Deduplicate by normalized title — same game, different source IDs."""
    seen = set()
    out = []
    for m in matches:
        key = m["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out

def pick_top5_with_ai(all_matches: list[dict], today: datetime) -> list[dict]:
    """Use GPT-4o to select the 5 most nationally prominent games today."""
    import os
    import requests as _req
    from dotenv import load_dotenv
    load_dotenv()

    if not all_matches:
        return []

    # Build a numbered list for GPT to reference
    match_lines = []
    for i, m in enumerate(all_matches):
        time_str = m.get("kickoff_local", "TBD")
        cat = m.get("category", "").replace("-", " ")
        match_lines.append(f"{i}: {m['title']} ({cat}) @ {time_str}")

    match_text = "\n".join(match_lines)
    date_str = today.strftime("%A, %B %d, %Y")

    prompt = f"""Today is {date_str}. Here are all the sports matches happening today:

{match_text}

Pick the 5 matches that will get the most national American sports attention today. Consider:
- Playoff games, championship games, rivalry matchups
- High-profile teams (big markets, star players, championship contenders)
- Cross-sport prominence (e.g. an NBA playoff game beats a regular season baseball game)
- Primetime scheduling

Respond with ONLY a JSON array of the index numbers, e.g.: [3, 7, 12, 18, 24]
No explanation. Just the JSON array."""

    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            },
            json={
                "model": "gpt-4o",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip any markdown fences
        content = content.replace("```json", "").replace("```", "").strip()
        indices = json.loads(content)
        result = [all_matches[i] for i in indices if 0 <= i < len(all_matches)]
        print(f"  AI selected top 5 indices: {indices}")
        return result
    except Exception as e:
        print(f"  Warning: AI top5 selection failed ({e}), falling back to popular[:5]")
        return [m for m in all_matches if m.get("popular")][:5]

def main() -> None:
    print("Fetching today's matches from streamed.pk...")

    today_matches = fetch_json(f"{API_BASE}/matches/all-today") or []
    live_matches  = fetch_json(f"{API_BASE}/matches/live") or []

    print(f"  Today: {len(today_matches)} matches")
    print(f"  Live:  {len(live_matches)} matches")

    live_ids = {m.get("id") for m in live_matches}

    my_team_matches = []
    popular_matches = []
    seen_ids = set()

    for match in today_matches + live_matches:
        mid = match.get("id", "")
        if mid in seen_ids:
            continue
        seen_ids.add(mid)

        norm = normalize_match(match)
        norm["is_live"] = mid in live_ids

        mine, label = is_my_team(match)
        if mine:
            norm["team_label"] = label
            my_team_matches.append(norm)
        elif match.get("popular"):
            popular_matches.append(norm)

    # Deduplicate both lists by title
    my_team_matches = dedup(my_team_matches)
    popular_matches = dedup(popular_matches)

    def sort_key(m):
        return (0 if m["is_live"] else 1, m.get("kickoff_utc") or "")

    my_team_matches.sort(key=sort_key)
    popular_matches.sort(key=sort_key)

# Ask GPT to pick the top 5 most nationally prominent games
    top5 = pick_top5_with_ai(popular_matches + my_team_matches, today=datetime.now(timezone.utc))

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "my_teams": my_team_matches,
        "top5": top5,
        "popular": popular_matches,
    }

    OUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"\n  Your teams playing today: {len(my_team_matches)}")
    for m in my_team_matches:
        live_tag = " 🔴 LIVE" if m["is_live"] else f" @ {m.get('kickoff_local', '?')}"
        print(f"    {m['team_label']} — {m['title']}{live_tag}")
    print(f"\n  Top 5 popular:")
    for m in popular_matches[:5]:
        live_tag = " 🔴 LIVE" if m["is_live"] else f" @ {m.get('kickoff_local', '?')}"
        print(f"    {m['title']}{live_tag}")
    print(f"\n  Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
