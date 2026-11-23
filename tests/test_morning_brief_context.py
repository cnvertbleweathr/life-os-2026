"""
context.py: grouping, news capping, notes, fixtures. No warehouse needed.

  uv run --with pytest pytest tests/test_morning_brief_context.py -q
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.morning_brief import context as C  # noqa: E402

TODAY = date(2026, 11, 21)


def row(domain, ref, kind, facts, *, item_date=TODAY, title="t", url=None,
        already_featured=None, featured_on=None, built_for=TODAY):
    return {"domain": domain, "ref": ref, "item_date": item_date, "kind": kind, "title": title,
            "url": url, "facts": json.dumps(facts), "already_featured": already_featured,
            "featured_on": featured_on, "built_for": built_for}


def test_groups_by_domain_and_drops_null_facts():
    ctx = C.build_context([
        row("fitness", "strava:1", "activity", {"distance_miles": 5.03, "avg_hr": None},
            url="https://www.strava.com/activities/1"),
        row("cfb_picks", "picks:season:2026", "season_record", {"wins": 22}, item_date=None),
    ], TODAY)
    assert set(ctx["domains"]) >= {"fitness", "music", "cfb_picks", "cfb_games", "team_games", "news"}
    run = ctx["domains"]["fitness"]["items"][0]
    assert run["facts"] == {"distance_miles": 5.03}
    assert run["url"] == "https://www.strava.com/activities/1"
    assert "already_featured" not in run           # news-only fields
    assert ctx["domains"]["cfb_picks"]["items"][0]["date"] is None
    assert ctx["domains"]["music"]["notes"] == ["Nothing in this domain this week."]
    assert ctx["warnings"] == []


def test_items_say_which_weekday_they_were():
    # 2026-11-23: items carried only "2026-11-17". The judge called Tuesday's squats
    # "Monday's" and marked a correct edition down; the writer called them "yesterday's".
    # Say the weekday and how long ago, so neither model has to work it out.
    monday = date(2026, 11, 23)
    ctx = C.build_context([
        row("fitness", "sugarwod:a", "crossfit", {}, item_date=date(2026, 11, 17), built_for=monday),
        row("fitness", "strava:b", "activity", {}, item_date=date(2026, 11, 22), built_for=monday),
        row("fitness", "fitness:c", "training_load", {}, item_date=monday, built_for=monday),
        row("team_games", "nba:d", "game", {}, item_date=date(2026, 11, 24), built_for=monday),
        row("team_games", "nba:e", "game", {}, item_date=date(2026, 11, 26), built_for=monday),
        row("cfb_picks", "picks:season", "season_record", {}, item_date=None, built_for=monday),
    ], monday)
    when = {it["ref"]: it.get("when") for d in ctx["domains"].values() for it in d["items"]}
    assert when == {
        "sugarwod:a": "Tuesday, Nov 17 (6 days ago)",
        "strava:b": "Sunday, Nov 22 (yesterday)",
        "fitness:c": "Monday, Nov 23 (today)",
        "nba:d": "Tuesday, Nov 24 (tomorrow)",
        "nba:e": "Thursday, Nov 26 (in 3 days)",
        "picks:season": None,
    }


def test_news_cap_prefers_unfeatured_then_newest():
    rows = [
        row("news", f"news:{i}", "science", {"summary": "s"}, item_date=TODAY - timedelta(days=i % 7),
            url=f"https://x/{i}", already_featured=(i < 5), featured_on=(TODAY if i < 5 else None))
        for i in range(25)
    ]
    items = C.build_context(rows, TODAY)["domains"]["news"]["items"]
    assert len(items) == C.NEWS_PER_CATEGORY
    assert not any(i["already_featured"] for i in items)       # 20 unfeatured beat 5 featured
    dates = [i["date"] for i in items]
    assert dates == sorted(dates, reverse=True)
    featured = C.build_context(rows[:3], TODAY)["domains"]["news"]
    assert featured["items"][0]["featured_on"] == TODAY.isoformat()
    assert "follow-up" in featured["notes"][0]


def test_long_summaries_are_trimmed():
    item = C.build_context([row("news", "news:1", "good_news", {"summary": "word " * 200},
                                already_featured=False)], TODAY)["domains"]["news"]["items"][0]
    assert len(item["facts"]["summary"]) <= C.NEWS_SUMMARY_CHARS + 1


def test_notes_flag_stale_music_pending_picks_and_games_today():
    ctx = C.build_context([
        row("music", "music:week", "week_summary", {"plays": 0, "newest_play_date": "2026-10-28"}),
        row("cfb_picks", "pick:1", "pick", {"outcome": "pending"}),
        row("cfb_games", "cfb_game:1", "upcoming_game", {"team": "UCF"}),
    ], TODAY)
    assert "2026-10-28" in ctx["domains"]["music"]["notes"][0]
    assert "pending" in ctx["domains"]["cfb_picks"]["notes"][0]
    assert "plays today" in ctx["domains"]["cfb_games"]["notes"][0]


def test_warns_when_dbt_did_not_run_today():
    ctx = C.build_context([row("fitness", "fitness:week", "week_summary", {}, built_for=TODAY - timedelta(days=1))], TODAY)
    assert "dbt hasn't run today" in ctx["warnings"][0]


def test_sample_fixture_loads_and_refs_are_unique():
    ctx = C.load_fixture()
    all_items = [it for b in ctx["domains"].values() for it in b["items"]]
    refs = C.refs(ctx)
    assert len(refs) == len(all_items)
    assert "https://example.org/good/otters" in C.urls(ctx)
    assert set(ctx["domains"]) == set(C.DOMAINS)


def test_cli_fixture_summary(capsys):
    assert C.main(["--fixture", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "news" in out and "tokens" in out
