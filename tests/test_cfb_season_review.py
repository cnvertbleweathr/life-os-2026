"""cfb_season_review helpers, the bet-team parser fix, and the live report on a fake warehouse."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cfb_season_review as rev  # noqa: E402
from grade_picks import backed_team_of, grade_one_pick  # noqa: E402


@pytest.mark.parametrize("bet,home,away,want", [
    ("Iowa State +3.0 (away dog)", "Iowa", "Iowa State", "Iowa State"),   # the bug
    ("Iowa -3.0 (home fav)", "Iowa", "Iowa State", "Iowa"),
    ("Kansas State -7.0 (away fav)", "Kansas", "Kansas State", "Kansas State"),
    ("Georgia Tech +10.5 (home dog)", "Georgia Tech", "Georgia", "Georgia Tech"),
    ("Notre Dame -20.5 (away fav)", "Navy", "Notre Dame", "Notre Dame"),
    ("Somebody Else -3", "Navy", "Notre Dame", None),
])
def test_backed_team_longest_match(bet, home, away, want):
    assert backed_team_of(bet, home, away) == want


def test_iowa_state_pick_graded_for_iowa_state():
    # Iowa State @ Iowa, Iowa favoured by 3, Iowa wins by 1: Iowa State +3 covers.
    pick = {"matchup": "Iowa State @ Iowa", "line": "-3.0 (DraftKings)",
            "bet": "Iowa State +3.0 (away dog)"}
    assert grade_one_pick(pick, home_score=21, away_score=20)["outcome"] == "win"


def test_stats_helpers():
    lo, hi = rev.wilson(15, 20)
    assert 0.53 < lo < 0.55 and 0.88 < hi < 0.90
    assert rev.binom_le(20, 20, 0.5) == pytest.approx(1.0)
    assert rev.binom_le(0, 3, 0.5) == pytest.approx(0.125)
    assert rev.side_of("Navy +7.0 (home dog)") == "home dog"
    assert rev.score_band(84) == "80-89" and rev.bucket(0.2) == "Strong" and rev.bucket(-0.3) == "Weak"


@pytest.fixture()
def warehouse(tmp_path, monkeypatch):
    path = tmp_path / "ons.duckdb"
    c = duckdb.connect(str(path))
    c.execute("CREATE SCHEMA cfbd; CREATE SCHEMA main_marts")
    c.execute("""CREATE TABLE cfbd.live_picks (season BIGINT, week BIGINT, matchup VARCHAR, bet VARCHAR,
                 bet_type VARCHAR, line VARCHAR, model_score BIGINT, n_edges BIGINT,
                 meets_publish_bar BOOLEAN, outcome VARCHAR, pnl DOUBLE, home_score BIGINT, away_score BIGINT)""")
    c.execute("""CREATE TABLE main_marts.mart_cfb_live_strength
                 (team VARCHAR, season BIGINT, week BIGINT, off_vs_preseason DOUBLE)""")
    rows = [
        # week, matchup, bet, line, score, publish, outcome, pnl, home, away
        (3, "Navy @ Notre Dame", "Notre Dame -20.5 (home fav)", "-20.5 (DK)", 88, True, "win", 0.909, 35, 7),
        (4, "Utah @ BYU", "Utah -3.0 (away fav)", "3.0 (DK)", 75, True, "loss", -1.0, 24, 20),
        # Stored as a loss by the old parser; actually Iowa State +3 covered (Iowa won by 1).
        (5, "Iowa State @ Iowa", "Iowa State +3.0 (away dog)", "-3.0 (DK)", 91, True, "loss", -1.0, 21, 20),
        (5, "Army @ Navy", "Navy -4.0 (home fav)", "-4.0 (DK)", 60, False, "win", 0.909, 28, 14),
        (9, "Duke @ UNC", "Duke +2.5 (away dog)", "-2.5 (DK)", 80, True, None, None, None, None),
    ]
    for w, m, b, l, s, pub, o, pnl, h, a in rows:
        c.execute("INSERT INTO cfbd.live_picks VALUES (2026, ?, ?, ?, 'EDGE', ?, ?, 4, ?, ?, ?, ?, ?)",
                  [w, m, b, l, s, pub, o, pnl, h, a])
    c.executemany("INSERT INTO main_marts.mart_cfb_live_strength VALUES (?, 2026, ?, ?)",
                  [("Notre Dame", 2, 0.30), ("Utah", 3, -0.20), ("Iowa State", 4, 0.05)])
    c.close()
    monkeypatch.setattr(rev, "DB_PATH", str(path))
    return path


def test_live_report(warehouse, capsys, monkeypatch, tmp_path):
    out = tmp_path / "report.md"
    monkeypatch.setattr("sys.argv", ["cfb_season_review.py", "--skip-history", "--out", str(out)])
    assert rev.main() == 0
    text = capsys.readouterr().out
    assert "graded through week 5" in text
    assert "Live published picks" in text and "1-2" in text           # stored outcomes
    assert "Iowa State @ Iowa" in text and "graded against the wrong team" in text
    assert "Strong (> +0.15)" in text
    assert out.read_text().startswith("```")


def test_regrade_repairs_history_file(tmp_path):
    import json
    from grade_picks import regrade_history_file
    f = tmp_path / "2026_wk05.json"
    f.write_text(json.dumps({"season": 2026, "week": 5, "games": [
        {"matchup": "Iowa State @ Iowa", "line": "-3.0 (DK)", "bet": "Iowa State +3.0 (away dog)",
         "outcome": "loss", "pnl": -1.0, "home_score": 21, "away_score": 20},
        {"matchup": "Navy @ Notre Dame", "line": "-20.5 (DK)", "bet": "Notre Dame -20.5 (home fav)",
         "outcome": "win", "pnl": 0.909, "home_score": 35, "away_score": 7},
        {"matchup": "Duke @ UNC", "line": "-2.5 (DK)", "bet": "Duke +2.5 (away dog)", "outcome": "pending"},
    ]}))
    assert len(regrade_history_file(f, dry_run=True)) == 1
    assert json.loads(f.read_text())["games"][0]["outcome"] == "loss"      # dry run wrote nothing
    changes = regrade_history_file(f, dry_run=False)
    assert changes == [{"file": "2026_wk05.json", "matchup": "Iowa State @ Iowa",
                        "bet": "Iowa State +3.0 (away dog)", "was": "loss", "now": "win"}]
    g = json.loads(f.read_text())["games"]
    assert g[0]["outcome"] == "win" and g[0]["pnl"] == 0.909 and g[0]["previous_outcome"] == "loss"
    assert g[1]["outcome"] == "win" and "previous_outcome" not in g[1]
    assert regrade_history_file(f, dry_run=False) == []                    # idempotent
