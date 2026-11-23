"""
checkin/build_packet: deterministic packet from made-up inputs (no warehouse, git or gh).

  uv run --with pytest pytest tests/test_checkin_build_packet.py -q
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from checkin import build_packet as bp

TODAY = date(2026, 3, 11)   # a Wednesday

PRIORITIES = """# Priorities

<!-- template note that should not appear -->

## This week's priorities

- Finish the garden planter
- Run three times

## ONS

- Check-in packet

## Work

- Quarterly review

## Personal

-

## Parking lot

- Learn sourdough
"""

ROADMAP = """
- 🟡 **In Progress** — legend line, not a table row
| Status | Item | Notes |
|---|---|---|
| 🟡 | Token health checks | Detect expired auth |
| 🟢 | Done thing | shipped |
| Sample source | 🔴 | Upstream is down |
| 1 | Some course (Author) | 8h | 🟡 20% |
"""


def ctx_row(domain, kind, day, title, **facts):
    return {"domain": domain, "kind": kind, "item_date": day, "title": title,
            "ref": f"{domain}:{title}", "facts": json.dumps(facts)}


def make_inputs(**over) -> bp.Inputs:
    base = dict(
        today=TODAY,
        priorities=PRIORITIES,
        context=[
            ctx_row("fitness", "activity", date(2026, 3, 9), "Evening Run", distance_miles=3.1),
            ctx_row("fitness", "crossfit", date(2026, 3, 8), "Back Squat", pr=True),
            ctx_row("fitness", "crossfit", date(2026, 3, 8), "Metcon", pr=False),
            ctx_row("fitness", "crossfit", date(2026, 3, 1), "Too old", pr=True),
            ctx_row("fitness", "week_summary", TODAY, "Training week", newest_activity_date="2026-03-09"),
            ctx_row("music", "top_artist", TODAY, "Artist Two", rank=2),
            ctx_row("music", "top_artist", TODAY, "Artist One", rank=1),
            ctx_row("cfb_picks", "week_record", date(2026, 3, 1), "Week 1", week=1, wins=1, losses=3, units=-2.2),
            ctx_row("cfb_picks", "week_record", date(2026, 3, 8), "Week 2", week=2, wins=3, losses=1, pushes=1, units=1.5),
            ctx_row("cfb_picks", "season_record", None, "Season", wins=4, losses=4, pushes=1, units=-0.7),
            ctx_row("cfb_games", "game", date(2026, 3, 7), "Home U vs Rival", team="Home U", opponent="Rival",
                    team_points=17, opp_points=20, result="L", record_after="5-4"),
            ctx_row("team_games", "game", date(2026, 3, 9), "SAM vs OPP", team="SAM", team_name="Sample City Comets",
                    opponent="OPP", venue="home", team_score=3, opp_score=2, result="W", season_record="10-5"),
        ],
        habits=[
            {"log_date": "2026-03-08", "meditation": 1, "pushups_100": 1, "nonfiction_pages_10": 0,
             "fiction_pages_10": 1, "daily_completion_pct": 75.0},
            {"log_date": "2026-03-10", "meditation": 0, "pushups_100": 1, "nonfiction_pages_10": 0,
             "fiction_pages_10": 1, "daily_completion_pct": 50.0},
        ],
        brief={"status": "published", "revisions": 1, "cost_usd": 0.12,
               "edition": {"lead_headline": "Comets Edge Opponents"}},
        commits=[{"sha": "abc", "date": "2026-03-10", "subject": "Check-in packet step 2"}],
        merged_prs=[{"number": 7, "title": "Add check-in packet"}],
        open_prs=[{"number": 8, "title": "New thing", "createdAt": "2026-03-10T00:00:00Z", "headRefName": "feat/x"},
                  {"number": 2, "title": "bump", "createdAt": "2026-01-01T00:00:00Z", "headRefName": "dependabot/pip/x"}],
        roadmap=ROADMAP,
        last_post=date(2026, 3, 9),
        last_app_checkin=date(2026, 3, 10),
    )
    base.update(over)
    return bp.Inputs(**base)


def test_header_and_priorities_verbatim():
    text = bp.build_packet(make_inputs())
    assert text.startswith("# Check-in — Wednesday, Mar 11, 2026\n")
    assert "Days since last check-in: 2 (last packet 2026-03-09)" in text
    assert "App check-in log: last entry 2026-03-10, 1 day ago" in text
    assert "## This week's priorities\n\n- Finish the garden planter\n- Run three times" in text
    assert "## Parking lot\n\n- Learn sourdough" in text
    assert "template note" not in text and "# Priorities" not in text


def test_first_packet_and_blank_template():
    template = (bp.ROOT / "checkin" / "priorities.template.md").read_text()
    text = bp.build_packet(make_inputs(last_post=None, priorities=template))
    assert "Days since last check-in: first packet" in text
    assert "_priorities.md is still the blank template._" in text


def test_tracking_highlights():
    text = bp.build_packet(make_inputs())
    assert "*Workouts:* 2 — 1 Strava (5.0 km), 1 SugarWOD session (2 workouts, 1 PR)" in text
    assert "*Top artists:* Artist One, Artist Two" in text
    assert "*CFB picks, week 2:* 3-1-1, +1.50u (season 4-4-1, -0.70u)" in text
    assert "Home U lost to Rival 20-17 (5-4)" in text          # winner first
    assert "Comets 1-0: W 3-2 vs OPP (10-5)" in text


def test_music_falls_back_when_no_plays():
    inp = make_inputs()
    inp.context = [r for r in inp.context if r["domain"] != "music"]
    inp.context.append(ctx_row("music", "week_summary", TODAY, "Listening week", newest_play_date="2026-01-02"))
    assert "*Music:* no plays this week (newest export play 2026-01-02)" in bp.build_packet(inp)


def test_habits_counts_and_broken_streak():
    text = bp.build_packet(make_inputs())
    assert "Logged 2 of 7 days, 62% average completion" in text
    assert "meditation 1/2, pushups_100 2/2, nonfiction_pages_10 0/2, fiction_pages_10 2/2" in text
    assert "Streak broken on 2026-03-10: meditation" in text


def test_habit_mart_lag_is_flagged():
    text = bp.build_packet(make_inputs(habits_log_latest=date(2026, 3, 11)))
    assert "The mart lags the habit log" in text


def test_brief_status():
    assert '"Comets Edge Opponents" — *pass*, 1 revision, $0.12' in bp.build_packet(make_inputs())
    text = bp.build_packet(make_inputs(brief={"status": "needs_review", "revisions": 2,
                                              "edition": {"lead_headline": "X"}}))
    assert "*needs_review*" in text
    assert "needs_review. Read it" in text.split("## Talking points")[1]


def test_build_status_and_roadmap():
    text = bp.build_packet(make_inputs())
    assert "- 1 commit in 7 days\n  - Check-in packet step 2" in text
    assert "- Merged: #7 Add check-in packet" in text
    assert "Opened this week, still open: #8 New thing (1 older Dependabot PRs open)" in text
    assert bp.roadmap_items(ROADMAP) == [("🔴", "Sample source"), ("🟡", "Token health checks"),
                                         ("🟡", "Some course (Author)")]


def test_git_unavailable_is_shown_not_fatal():
    text = bp.build_packet(make_inputs(commits=None, merged_prs=None, open_prs=None))
    assert "git unavailable" in text and "gh unavailable" in text


def test_priority_without_activity_becomes_a_talking_point():
    points = bp.build_packet(make_inputs()).split("## Talking points")[1]
    assert 'No activity this week on the priority "Finish the garden planter"' in points
    assert "Run three times" not in points                    # a run was logged


def test_exactly_three_talking_points_with_fallback():
    inp = make_inputs(priorities=None, roadmap=None, habits=[], brief={"status": "published",
                      "edition": {"lead_headline": "Fine"}})
    inp.context = [r for r in inp.context if r["kind"] != "week_summary"]
    points = bp.build_packet(inp).split("## Talking points\n")[1].strip().splitlines()
    assert [p[:3] for p in points] == ["1. ", "2. ", "3. "]


def test_stays_under_limit_with_plus_n_more():
    many = [{"sha": str(i), "date": "2026-03-10", "subject": f"Commit number {i} " + "x" * 60} for i in range(40)]
    long_roadmap = "\n".join(f"| 🟡 | Item {i} {'y' * 50} | notes |" for i in range(40))
    text = bp.build_packet(make_inputs(commits=many, roadmap=long_roadmap))
    assert len(text) <= bp.MAX_CHARS
    build = text.split("## ONS build")[1]
    assert "  - +3" in build and " more" in build          # both lists cut, smallest limit first tried that fits
    assert "## Talking points" in text


def test_save_writes_dated_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    path = bp.save("hello\n", TODAY)
    assert path == tmp_path / "checkin" / "2026-03-11.md"
    assert path.read_text() == "hello\n"


def test_last_post_reads_only_successful_earlier_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    log = tmp_path / "checkin" / "packet_posts.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("\n".join(json.dumps(r) for r in [
        {"date": "2026-03-05", "ok": True},
        {"date": "2026-03-09", "ok": False},
        {"date": "2026-03-11", "ok": True},      # today's own post doesn't count
    ]) + "\n")
    monkeypatch.setattr(bp, "load_warehouse", lambda inp, db_path=None: None)
    monkeypatch.setattr(bp, "load_git", lambda inp: None)
    monkeypatch.setattr(bp, "PRIORITIES", tmp_path / "missing.md")
    inp = bp.gather(TODAY)
    assert inp.last_post == date(2026, 3, 5)
    assert inp.priorities is None
