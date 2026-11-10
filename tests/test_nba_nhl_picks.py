"""NBA / NHL daily picks: paper-entry grading, CLV, idempotence and append-only capture.

No rule is validated yet, so a live day rarely produces a paper entry; these tests
pin the grading math on synthetic records instead.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import nba_nhl_generate_picks as gen  # noqa: E402
import nba_nhl_grade_picks as grade  # noqa: E402


def final(**kw):
    base = dict(game_id="g1", completed=True, status="STATUS_FINAL", home_score=118, away_score=112,
                went_ot=False, shootout=False, book="Draft Kings", line_snapshot="close",
                home_spread=-4.5, home_spread_price=-110.0, away_spread_price=-110.0,
                home_ml=-180.0, away_ml=150.0, total=223.5, over_price=-110.0, under_price=-110.0)
    base.update(kw)
    return SimpleNamespace(**base)


def record(side="OVER", captured=220.5, price=-110.0, fires=True):
    return {"game_id": "g1", "matchup": "AWY @ HOM", "home_team": "HOM", "away_team": "AWY",
            "verdict": "NO_BET", "bet": None,
            "paper": {"test": "nba_totals_open_v1", "fires": fires, "side": side if fires else None,
                      "pred_total": 233.0, "captured_total": captured, "gap": 12.5,
                      "price": price if fires else None, "prices_in_band": True}}


def test_paper_over_win_pnl_and_clv():
    g = record("OVER", 220.5, -110.0)
    assert grade.grade_game(g, final(), "nba", "2026-11-10T12:00:00+00:00")
    pe = g["paper"]
    assert pe["outcome"] == "win"                       # 230 points > 220.5
    assert abs(pe["pnl"] - 100 / 110) < 1e-3
    assert pe["clv"] == 3.0                             # closed 223.5: the over at 220.5 beat the close
    assert (g["home_score"], g["away_score"], g["closing_total"]) == (118, 112, 223.5)


def test_paper_under_loss_negative_clv():
    g = record("UNDER", 220.5, +100.0)
    grade.grade_game(g, final(), "nba", "now")
    assert g["paper"]["outcome"] == "loss" and g["paper"]["pnl"] == -1.0
    assert g["paper"]["clv"] == -3.0


def test_paper_push_and_plus_price():
    g = record("OVER", 230.0, +105.0)
    grade.grade_game(g, final(), "nba", "now")
    assert g["paper"]["outcome"] == "push" and g["paper"]["pnl"] == 0.0
    assert grade.settle_total("UNDER", 229.5, +105.0, 220) == ("win", 1.05)


def test_no_paper_entry_still_records_close():
    g = record(fires=False)
    assert grade.grade_game(g, final(), "nba", "now")
    assert "outcome" not in g["paper"] and g["closing_home_spread"] == -4.5


def test_idempotent_and_waits_for_final():
    g = record()
    assert not grade.grade_game(g, final(completed=False, status="STATUS_IN_PROGRESS"), "nba", "now")
    assert "graded_at" not in g
    assert grade.grade_game(g, final(), "nba", "t1")
    assert not grade.grade_game(g, final(home_score=0), "nba", "t2")     # already graded: untouched
    assert g["home_score"] == 118 and g["graded_at"] == "t1"


def test_canceled_game_is_marked_not_graded():
    g = record()
    assert grade.grade_game(g, final(completed=False, status="STATUS_POSTPONED"), "nba", "now")
    assert g["final_status"] == "STATUS_POSTPONED" and "graded_at" not in g
    assert "outcome" not in g["paper"]


def test_append_only_keeps_first_capture(tmp_path):
    path = tmp_path / "2026-11-10.json"
    first = [{"game_id": "g1", "league": "nba", "total": 220.5}]
    data, added = gen.merge_append_only(path, first)
    assert added == 1
    path.write_text(json.dumps(data))
    later = [{"game_id": "g1", "league": "nba", "total": 224.5}, {"game_id": "g2", "league": "nba", "total": 230.0}]
    data, added = gen.merge_append_only(path, later)
    assert added == 1
    assert [g["total"] for g in data["games"]] == [220.5, 230.0]       # g1 keeps its first capture
