#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml


def load_goals(goal_path: Path) -> dict:
    if not goal_path.exists():
        return {}
    with open(goal_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def safe_get(d: dict, path: list, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()

    root = Path(__file__).resolve().parents[1]
    in_path = root / "data" / "spotify" / "processed" / "streams_clean.csv"
    out_dir = root / "data" / "spotify" / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"spotify_summary_{args.year}.csv"

    if not in_path.exists():
        raise SystemExit(f"Missing {in_path}. Run scripts/spotify_ingest_streaming.py first.")

    df = pd.read_csv(in_path)

    # Expect at least: played_at_utc, ms_played, track_name, artist_name, track_uri
    # Be forgiving about column names.
    played_col = "played_at_utc" if "played_at_utc" in df.columns else "played_at"
    ms_col = "ms_played" if "ms_played" in df.columns else "msPlayed"

    if played_col not in df.columns or ms_col not in df.columns:
        raise SystemExit(f"Missing required columns. Found: {list(df.columns)[:50]}")

    # Parse timestamps as UTC
    df[played_col] = pd.to_datetime(df[played_col], errors="coerce", utc=True)
    df = df.dropna(subset=[played_col])

    start = datetime(args.year, 1, 1, tzinfo=timezone.utc)
    end = datetime(args.year + 1, 1, 1, tzinfo=timezone.utc)
    ytd = df[(df[played_col] >= start) & (df[played_col] < end)].copy()

    if ytd.empty:
        minutes = 0.0
        days = 0
        unique_artists = 0
        unique_tracks = 0
        top_artist = ""
        top_track = ""
    else:
        ytd[ms_col] = pd.to_numeric(ytd[ms_col], errors="coerce").fillna(0)
        minutes = float(ytd[ms_col].sum() / 60000.0)

        # Days listened
        ytd["day"] = ytd[played_col].dt.date
        days = int(ytd["day"].nunique())

        # Uniques
        artist_col = "artist_name" if "artist_name" in ytd.columns else ("artistName" if "artistName" in ytd.columns else None)
        track_col = "track_name" if "track_name" in ytd.columns else ("trackName" if "trackName" in ytd.columns else None)
        uri_col = "track_uri" if "track_uri" in ytd.columns else ("spotifyTrackUri" if "spotifyTrackUri" in ytd.columns else None)

        if artist_col:
            unique_artists = int(ytd[artist_col].dropna().nunique())
            artist_counts = Counter([a for a in ytd[artist_col].dropna().astype(str)])
            top_artist = artist_counts.most_common(1)[0][0] if artist_counts else ""
        else:
            unique_artists = 0
            top_artist = ""

        # prefer uri uniqueness if available; else name
        if uri_col and uri_col in ytd.columns:
            unique_tracks = int(ytd[uri_col].dropna().nunique())
        elif track_col and track_col in ytd.columns:
            unique_tracks = int(ytd[track_col].dropna().nunique())
        else:
            unique_tracks = 0

        if track_col and track_col in ytd.columns:
            track_counts = Counter([t for t in ytd[track_col].dropna().astype(str)])
            top_track = track_counts.most_common(1)[0][0] if track_counts else ""
        else:
            top_track = ""

    # goals
    goals = load_goals(root / "goals" / "2026.yaml")
    goal_minutes = (
        safe_get(goals, ["domains", "personal", "outcomes", "spotify_minutes"], None)
        or safe_get(goals, ["domains", "personal", "outcomes", "spotify_minutes_goal"], None)
        or 0
        )

    try:
        goal_minutes = float(goal_minutes)
    except Exception:
        goal_minutes = 0.0

    progress_pct = (minutes / goal_minutes * 100.0) if goal_minutes else 0.0

    row = {
        "year": args.year,
        "spotify_minutes_ytd": round(minutes, 2),
        "spotify_goal_minutes": round(goal_minutes, 2),
        "spotify_progress_pct": round(progress_pct, 2),
        "spotify_days_listened_ytd": days,
        "spotify_unique_artists_ytd": unique_artists,
        "spotify_unique_tracks_ytd": unique_tracks,
        "spotify_top_artist_ytd": top_artist,
        "spotify_top_track_ytd": top_track,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)

    print(f"Wrote: {out_path}")
    print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
