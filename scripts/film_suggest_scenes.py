#!/usr/bin/env python3
"""
scripts/film_suggest_scenes.py: suggest a GIF scene for each watched film
that has no catalog row yet. Runs in the daily sync, after dbt.

For each new film in main_marts.mart_film_watches (most recently watched
first) it makes one Claude call (claude-haiku-5-5, structured output) asking
for the film's most iconic, visually distinctive moment: a short label, one
line on what moves in a 5-second loop, an approximate timestamp and a
confidence. The answer becomes a catalog row with status "suggested"
(api/film_catalog.py); the render mode comes from a fixed rule, not from the
model. Nothing renders until you approve the row.

Every call is logged to data/ai/generations.jsonl in the same shape as the
OpenClaw analyzers. The calls share OpenClaw's $5.00/month budget
(openclaw/config.py): before each call the script sums this month's cost_usd
in that log and stops if the budget is spent.

Usage:
  python scripts/film_suggest_scenes.py              # up to 50 films per run
  python scripts/film_suggest_scenes.py --limit 5
  python scripts/film_suggest_scenes.py --dry-run    # list films that would be asked about; no calls, no writes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api import film_catalog as fc  # noqa: E402
from api.store import JsonlLog, now_local  # noqa: E402

MODEL = "claude-haiku-5-5"
PRICE_PER_MTOK = {"input": 0.10, "output": 0.50}   # Haiku 5.5, prompts up to 100K tokens
MONTHLY_BUDGET_USD = 5.00                           # shared with OpenClaw (openclaw/config.py)
GENERATIONS_LOG = JsonlLog("ai", "generations.jsonl")
ANALYZER = "film_scene_suggest"

SYSTEM = (
    "You choose the single most iconic, visually distinctive moment of a film to become a "
    "5-second looping pixel-art GIF, 64x32 pixels. Prefer a moment with one clear subject and "
    "simple motion that reads at very low resolution (a silhouette crossing the frame, a door "
    "swinging open, a light flickering) over dialogue or busy crowd scenes. If you don't know the "
    "film well enough to name a real scene from it, say so with confidence \"low\" and keep the "
    "label generic rather than inventing a scene."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "scene_label": {
            "type": "string",
            "description": "Short name for the moment, under 60 characters, e.g. 'The shadow on the stairs'.",
        },
        "scene_note": {
            "type": "string",
            "description": "One line: what is in frame and what moves during the 5-second loop.",
        },
        "timestamp_s": {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
            "description": "Approximate seconds from the start of the film where the moment happens, or null if unsure.",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "How sure you are that this moment is real and that the timestamp is close.",
        },
    },
    "required": ["scene_label", "scene_note", "timestamp_s", "confidence"],
    "additionalProperties": False,
}

FILMS_SQL = """
with films as (
    select
        film_key,
        any_value(tmdb_id)    as tmdb_id,
        any_value(title)      as title,
        any_value(film_year)  as year,
        max(watch_date)       as last_watch
    from main_marts.mart_film_watches
    group by film_key
),
files as (
    select tmdb_id, lower(trim(title)) as title_norm, film_year,
           max(file_path) as file_path, max(duration_ms) as duration_ms
    from main_staging.stg_plex__history
    where in_library and file_path is not null
    group by 1, 2, 3
)
select
    f.film_key, f.tmdb_id, f.title, f.year, f.last_watch,
    coalesce(
        (select max(x.file_path) from files x where f.tmdb_id is not null and x.tmdb_id = f.tmdb_id),
        (select max(x.file_path) from files x
          where x.title_norm = lower(trim(f.title)) and x.film_year is not distinct from f.year)
    ) as plex_file,
    coalesce(
        (select max(x.duration_ms) from files x where f.tmdb_id is not null and x.tmdb_id = f.tmdb_id),
        (select max(x.duration_ms) from files x
          where x.title_norm = lower(trim(f.title)) and x.film_year is not distinct from f.year)
    ) as duration_ms
from films f
order by f.last_watch desc, f.film_key
"""


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


def watched_films(path: str) -> list[dict[str, Any]]:
    import duckdb
    with duckdb.connect(path, read_only=True) as con:
        cur = con.execute(FILMS_SQL)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def films_needing_suggestion(films: list[dict[str, Any]]) -> list[dict[str, Any]]:
    have = fc.catalog()
    return [f for f in films if f["film_key"] not in have]


def month_spend(now: datetime | None = None) -> float:
    month = (now or now_local()).strftime("%Y-%m")
    return round(sum(
        float(r.get("cost_usd") or 0)
        for r in GENERATIONS_LOG.rows()
        if str(r.get("timestamp", "")).startswith(month)
    ), 6)


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return round(tokens_in * PRICE_PER_MTOK["input"] / 1e6 + tokens_out * PRICE_PER_MTOK["output"] / 1e6, 6)


def log_generation(film_key: str, tokens_in: int, tokens_out: int, status: str,
                   error: str | None = None) -> None:
    """Same fields as openclaw/audit.py, plus model and film_key."""
    GENERATIONS_LOG.append({
        "timestamp":       datetime.now().isoformat(),
        "analyzer_name":   ANALYZER,
        "capability_used": "generate_text",
        "tables_read":     ["main_marts.mart_film_watches"],
        "tables_written":  ["film.scene_catalog"],
        "tokens_input":    tokens_in,
        "tokens_output":   tokens_out,
        "cost_usd":        cost_usd(tokens_in, tokens_out),
        "policy_enforced": True,
        "status":          status,
        "error_message":   error,
        "model":           MODEL,
        "film_key":        film_key,
    })


def prompt_for(film: dict[str, Any]) -> str:
    year = f" ({film['year']})" if film.get("year") else ""
    lines = [f"Film: {film['title']}{year}"]
    if film.get("duration_ms"):
        lines.append(f"Runtime of this copy: {round(film['duration_ms'] / 60000)} min "
                     f"({film['duration_ms'] // 1000} s); give timestamp_s within it.")
    lines.append("Pick the moment for its GIF.")
    return "\n".join(lines)


def clean(suggestion: dict[str, Any], film: dict[str, Any]) -> dict[str, Any]:
    """Drop a timestamp that can't be right: negative, or past the end of the file."""
    ts = suggestion.get("timestamp_s")
    runtime_s = (film.get("duration_ms") or 0) / 1000
    if ts is not None and (ts < 0 or (runtime_s and ts > runtime_s)):
        suggestion = {**suggestion, "timestamp_s": None}
    return suggestion


def claude_suggest(client) -> Callable[[dict[str, Any]], tuple[dict | None, int, int, str]]:
    """Returns suggest(film) -> (suggestion or None, tokens_in, tokens_out, status)."""

    def suggest(film: dict[str, Any]):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": prompt_for(film)}],
        )
        usage = response.usage
        if response.stop_reason != "end_turn":
            # refusal or max_tokens: no usable answer; the row lands empty for a manual fill
            return None, usage.input_tokens, usage.output_tokens, response.stop_reason
        text = next(b.text for b in response.content if b.type == "text")
        return clean(json.loads(text), film), usage.input_tokens, usage.output_tokens, "success"

    return suggest


def run(films: list[dict[str, Any]], suggest, limit: int, budget: float = MONTHLY_BUDGET_USD) -> dict[str, int]:
    """Suggest scenes for up to `limit` films, stopping when the month's budget is spent.
    A failed call writes no row, so the film is asked about again on the next run."""
    counts = {"suggested": 0, "empty": 0, "failed": 0, "skipped_budget": 0}
    for i, film in enumerate(films[:limit]):
        if month_spend() >= budget:
            counts["skipped_budget"] = len(films[:limit]) - i
            print(f"  Monthly AI budget (${budget:.2f}) spent; stopping.")
            break
        try:
            suggestion, t_in, t_out, status = suggest(film)
        except Exception as e:   # one film's failure shouldn't stop the rest
            log_generation(film["film_key"], 0, 0, "error", f"{type(e).__name__}: {e}")
            counts["failed"] += 1
            print(f"  ✗ {film['title']}: {type(e).__name__}: {e}")
            if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
                print("  Credentials rejected; stopping.")
                break
            continue
        log_generation(film["film_key"], t_in, t_out, status)
        fc.add_suggestion(film, suggestion, suggested_by=MODEL)
        if suggestion:
            counts["suggested"] += 1
            print(f"  ✓ {film['title']}: {suggestion['scene_label']} ({suggestion['confidence']})")
        else:
            counts["empty"] += 1
            print(f"  · {film['title']}: no suggestion ({status}); row added for a manual fill")
    return counts


def main() -> int:
    p = argparse.ArgumentParser(description="Suggest GIF scenes for newly watched films.")
    p.add_argument("--limit", type=int, default=50, help="most films to ask about this run")
    p.add_argument("--dry-run", action="store_true", help="list the films; no calls, no writes")
    args = p.parse_args()

    try:
        films = films_needing_suggestion(watched_films(db_path()))
    except Exception as e:
        print(f"Film scene suggestions: can't read mart_film_watches ({e}); skipping.")
        return 0
    print(f"Film scene suggestions: {len(films)} films without a catalog row; "
          f"month's AI spend ${month_spend():.4f} of ${MONTHLY_BUDGET_USD:.2f}")

    if args.dry_run:
        for f in films[:args.limit]:
            mode = fc.default_render_mode(f["title"], f["year"], f["plex_file"])
            print(f"  [dry-run] {f['film_key']:<24} {f['title']} ({f['year']})  → {mode}")
        return 0
    if not films:
        return 0

    import anthropic
    counts = run(films, claude_suggest(anthropic.Anthropic()), args.limit)
    print(f"  {counts}")
    return 1 if counts["failed"] and not (counts["suggested"] or counts["empty"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
