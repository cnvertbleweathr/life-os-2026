#!/usr/bin/env python3
"""
track_news_signals.py

For each CFB game with significant line movement this week, queries NewsAPI
for team-specific news and classifies articles by type and signal strength.

Stores results in cfbd.news_signals linked by game_id so they join with
cfbd.line_history and mart_cfbd_line_movement.

Signal classification:
  INJURY_QB        — 10  (starter injury, highest impact)
  INJURY_SKILL     — 7   (WR, RB, TE injury)
  INJURY_OL        — 5   (offensive line)
  INJURY_DEF       — 4   (defensive player)
  SUSPENSION       — 8   (eligibility/suspension)
  DEPTH_CHART      — 6   (starting lineup change)
  WEATHER          — 5   (forecast for outdoor game)
  COACHING         — 4   (coordinator news, game plan)
  TRANSFER_PORTAL  — 3   (late portal activity)
  GENERAL          — 1   (noise)

Run: Wed/Thu during season, after track_lines.py has identified movers.

Usage:
  python scripts/track_news_signals.py              # current week
  python scripts/track_news_signals.py --week 3 --year 2026 --min-move 0.5
  python scripts/track_news_signals.py --dry-run    # print without writing
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
load_dotenv(ROOT / ".env")

NEWS_API_KEY  = os.getenv("NEWS_API_KEY", "")
CFBD_TOKEN    = os.getenv("CFBD_API_TOKEN", "")
API_BASE      = "https://api.collegefootballdata.com"

# ─────────────────────────────────────────────────────────────────────────────
# Signal classification
# ─────────────────────────────────────────────────────────────────────────────

# Keyword → (signal_type, base_strength)
# Matched against headline + description (lowercased)
SIGNAL_PATTERNS: list[tuple[str, str, int]] = [
    # QB injuries — highest impact
    (r"\bqb\b.*\b(injur|hurt|out|doubtful|questionable|miss)\b",  "INJURY_QB",       10),
    (r"\bquarterback\b.*\b(injur|hurt|out|doubtful|questionable)", "INJURY_QB",       10),
    (r"\b(injur|hurt|out|doubtful|questionable)\b.*\bqb\b",        "INJURY_QB",       10),
    (r"\b(injur|hurt|out|doubtful|questionable)\b.*\bquarterback",  "INJURY_QB",       10),

    # Skill position injuries
    (r"\b(wide receiver|wr|running back|rb|tight end|te)\b.*\b(injur|hurt|out)",  "INJURY_SKILL", 7),
    (r"\b(injur|hurt|out|doubtful)\b.*\b(wide receiver|wr|running back|rb)",      "INJURY_SKILL", 7),

    # OL injuries
    (r"\b(offensive line|center|guard|tackle)\b.*\b(injur|hurt|out)",  "INJURY_OL", 5),

    # Defensive injuries
    (r"\b(linebacker|corner|safety|defensive end|edge)\b.*\b(injur|hurt|out)",  "INJURY_DEF", 4),
    (r"\bdefensive\b.*\b(injur|hurt|out|doubtful)\b",                            "INJURY_DEF", 4),

    # Suspension / eligibility
    (r"\b(suspend|suspension|ineligible|eligibility|banned)\b",  "SUSPENSION", 8),
    (r"\b(ncaa investigation|dismissed|expelled)\b",              "SUSPENSION", 8),

    # Depth chart / lineup changes
    (r"\b(depth chart|starting lineup|starter|named starter|will start)\b",     "DEPTH_CHART", 6),
    (r"\b(benched|bench|replacing|replaces|emergency starter)\b",                "DEPTH_CHART", 6),

    # Transfer portal (late movement)
    (r"\b(transfer portal|entered portal|nil deal|decommit)\b",  "TRANSFER_PORTAL", 3),

    # Weather
    (r"\b(hurricane|tropical storm|severe weather|postpone|cancel)\b",           "WEATHER", 7),
    (r"\b(snow|blizzard|ice|frozen|wind advisory|wind warning)\b.*\b(game|kick)", "WEATHER", 5),

    # Coaching
    (r"\b(fired|resign|interim|offensive coordinator|defensive coordinator)\b",   "COACHING", 4),
    (r"\b(game plan|scheme change|coaching staff)\b",                             "COACHING", 3),

    # General injury (catch-all — lower weight)
    (r"\b(injur|injury|injured|hurt|out for|ruled out)\b",  "INJURY_GENERAL", 3),
]

# Position importance multiplier for QB context
QB_NAMES_BOOST = ["starting", "starter", "first string", "week 1"]


def classify_article(title: str, description: str) -> tuple[str, int]:
    """
    Returns (signal_type, strength) for the highest-matching pattern.
    strength 0 = no signal (general noise).
    """
    text = f"{title} {description or ''}".lower()

    best_type     = "GENERAL"
    best_strength = 0

    for pattern, sig_type, strength in SIGNAL_PATTERNS:
        if re.search(pattern, text):
            if strength > best_strength:
                best_strength = strength
                best_type     = sig_type

    return best_type, best_strength


def fetch_team_news(
    team: str,
    from_date: str,
    api_key: str,
    page_size: int = 5,
) -> list[dict]:
    """Fetch recent news articles for a team from NewsAPI."""
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        f'"{team}" football',
                "apiKey":   api_key,
                "from":     from_date,
                "pageSize": page_size,
                "sortBy":   "relevancy",
                "language": "en",
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  NewsAPI error for {team}: {e}", file=sys.stderr)
        return []


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS cfbd")
    con.execute("""
        CREATE TABLE IF NOT EXISTS cfbd.news_signals (
            -- Game context
            game_id         BIGINT,
            season          INTEGER,
            week            INTEGER,
            home_team       VARCHAR,
            away_team       VARCHAR,
            team_affected   VARCHAR,  -- which team the article is about

            -- Line context at time of news fetch
            spread_at_fetch     DOUBLE,
            spread_open         DOUBLE,
            spread_movement     DOUBLE,  -- movement at time of news query

            -- Article
            title           VARCHAR,
            description     VARCHAR,
            source          VARCHAR,
            url             VARCHAR,
            published_at    VARCHAR,

            -- Classification
            signal_type     VARCHAR,  -- INJURY_QB, SUSPENSION, WEATHER, etc.
            signal_strength INTEGER,  -- 0-10

            -- Metadata
            fetched_at      TIMESTAMP,
            snapshot_date   DATE,

            PRIMARY KEY (game_id, url)
        )
    """)


def current_cfb_week(year: int) -> int | None:
    today = date.today()
    if today.month in (2, 3, 4, 5, 6, 7):
        return None
    season_start = date(year, 8, 24)
    delta        = (today - season_start).days
    if delta < 0:
        return None
    return min(delta // 7 + 1, 15)


def main() -> int:
    p = argparse.ArgumentParser(description="Track news signals for CFB line movers")
    p.add_argument("--year",      type=int,   default=date.today().year)
    p.add_argument("--week",      type=int,   default=None)
    p.add_argument("--min-move",  type=float, default=0.5,
                   help="Min absolute line movement to query news for (default 0.5)")
    p.add_argument("--all-games", action="store_true",
                   help="Query news for ALL games this week, not just movers")
    p.add_argument("--dry-run",   action="store_true")
    args = p.parse_args()
    if not NEWS_API_KEY:
        print("⚠️  NEWS_API_KEY not set — cannot fetch news signals", file=sys.stderr)
        return 1

    # Always ensure the table exists, even off-season, so downstream
    # dbt models can compile against an empty table rather than failing.
    _con = duckdb.connect(DB_PATH)
    ensure_table(_con)
    _con.close()

    year = args.year
    week = args.week or current_cfb_week(year)
    if week is None:
        print(f"Off-season ({date.today()}) — no games to track news for")
        return 0

    print(f"📰 Tracking news signals — {year} Week {week}")

    # ── Pull games with line movement from DuckDB ─────────────────────────
    try:
        con = duckdb.connect(DB_PATH)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}", file=sys.stderr)
        return 1

    # Query the line history for this week's games
    # Filter to significant movers unless --all-games
    move_filter = "" if args.all_games else f"AND abs(spread_movement) >= {args.min_move}"

    games = con.execute(f"""
        SELECT DISTINCT
            game_id, season, week, home_team, away_team,
            spread_latest, spread_open, spread_movement
        FROM cfbd.line_history
        WHERE season = {year}
          AND week   = {week}
          {move_filter}
          AND spread_movement IS NOT NULL
        ORDER BY abs(spread_movement) DESC
        LIMIT 30
    """).df()

    if games.empty:
        if args.all_games:
            # Fall back to just getting this week's games from the API
            print("No line history yet — fetching game list from CFBD API")
            games = _fetch_games_from_api(year, week)
        else:
            print(f"No significant movers (≥{args.min_move} pts) found in line history")
            print("Run with --all-games to query news for all games regardless of movement")
            return 0

    print(f"Found {len(games)} games to check")

    # NewsAPI free tier: 100 requests/day
    # Each game = 2 requests (home + away team)
    # Cap at 20 games = 40 requests, leaving headroom for other pages
    MAX_GAMES = 20
    if len(games) > MAX_GAMES:
        print(f"Capping at {MAX_GAMES} games to stay within NewsAPI rate limit")
        games = games.head(MAX_GAMES)

    # News window: articles from Monday of this week onward
    today          = date.today()
    week_start     = today - timedelta(days=today.weekday())  # Monday
    from_date      = week_start.isoformat()
    now            = datetime.now(timezone.utc)
    all_rows       = []
    total_articles = 0
    total_signals  = 0

    for _, game in games.iterrows():
        game_id    = int(game["game_id"])
        home       = str(game["home_team"])
        away       = str(game["away_team"])
        spread_now = game.get("spread_latest")
        spread_open = game.get("spread_open")
        spread_move = game.get("spread_movement")

        move_str = f" (moved {float(spread_move):+.1f})" if spread_move is not None else ""
        print(f"\n  {away} @ {home}{move_str}")

        for team in [home, away]:
            articles = fetch_team_news(team, from_date, NEWS_API_KEY, page_size=5)
            total_articles += len(articles)

            for article in articles:
                title   = article.get("title", "") or ""
                desc    = article.get("description", "") or ""
                source  = article.get("source", {}).get("name", "")
                url     = article.get("url", "")
                pub     = article.get("publishedAt", "")

                sig_type, sig_strength = classify_article(title, desc)

                if args.dry_run:
                    if sig_strength >= 3:  # only print meaningful signals
                        print(f"    [{sig_type} {sig_strength}] {title[:80]}")
                    continue

                all_rows.append({
                    "game_id":          game_id,
                    "season":           int(game["season"]),
                    "week":             int(game["week"]),
                    "home_team":        home,
                    "away_team":        away,
                    "team_affected":    team,
                    "spread_at_fetch":  float(spread_now)  if spread_now  is not None else None,
                    "spread_open":      float(spread_open) if spread_open is not None else None,
                    "spread_movement":  float(spread_move) if spread_move is not None else None,
                    "title":            title[:500],
                    "description":      desc[:500],
                    "source":           source,
                    "url":              url,
                    "published_at":     pub,
                    "signal_type":      sig_type,
                    "signal_strength":  sig_strength,
                    "fetched_at":       now.isoformat(),
                    "snapshot_date":    today.isoformat(),
                })

                if sig_strength >= 3:
                    total_signals += 1
                    print(f"    ⚡ [{sig_type} strength={sig_strength}] "
                          f"{source}: {title[:70]}")

    if args.dry_run:
        print(f"\nDRY RUN — would store {len(all_rows)} articles")
        return 0

    # Write to DuckDB
    if all_rows:
        import pandas as pd
        ensure_table(con)
        df = pd.DataFrame(all_rows)

        # Upsert: delete existing for same game + date, then insert
        game_ids = df["game_id"].unique().tolist()
        ids_str  = ",".join(str(g) for g in game_ids)
        con.execute(f"""
            DELETE FROM cfbd.news_signals
            WHERE game_id IN ({ids_str})
              AND snapshot_date = '{today.isoformat()}'
        """)
        con.execute("INSERT INTO cfbd.news_signals SELECT * FROM df")

    con.close()

    print(f"\n{'='*50}")
    print(f"Scanned {total_articles} articles across {len(games)} games")
    print(f"Found {total_signals} meaningful signals (strength ≥ 3)")
    print(f"Stored {len(all_rows)} total articles")
    return 0


def _fetch_games_from_api(year: int, week: int) -> "pd.DataFrame":
    """Fallback: fetch game list from CFBD when no line history exists yet."""
    import pandas as pd
    if not CFBD_TOKEN:
        return pd.DataFrame()
    try:
        r = requests.get(
            f"{API_BASE}/games",
            headers={"Authorization": f"Bearer {CFBD_TOKEN}"},
            params={"year": year, "week": week, "division": "fbs"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        rows = []
        for g in data:
            rows.append({
                "game_id":        g.get("id"),
                "season":         year,
                "week":           week,
                "home_team":      g.get("homeTeam") or g.get("home_team"),
                "away_team":      g.get("awayTeam") or g.get("away_team"),
                "spread_latest":  None,
                "spread_open":    None,
                "spread_movement": None,
            })
        return pd.DataFrame(rows).dropna(subset=["game_id", "home_team"])
    except Exception as e:
        print(f"CFBD API error: {e}", file=sys.stderr)
        return pd.DataFrame()


if __name__ == "__main__":
    raise SystemExit(main())
