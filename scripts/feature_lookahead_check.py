#!/usr/bin/env python3
"""
feature_lookahead_check.py

Independent check of the pregame feature marts (mart_nba_game_features,
mart_nhl_game_features). Recomputes rolling features in pandas straight from the
raw tables -- no dbt model, no SQL window -- for a random sample of games and
compares them with the marts:

  NBA (nba.team_game_logs)   ortg_l10, net_std, efg_l5, pace_l10, opp_orb_pct_std,
                             net_prior; days_rest, is_b2b, games_last7 from the raw
                             ESPN schedule (nba.games, 2014-15 on)
  NHL (nhl.moneypuck_team_games, nhl.goalie_games)
                             xgf_pct_5v5_l10, corsi_pct_5v5_std, pp_xgf60_std,
                             starter_sv_pct_l10

Each feature is computed only from rows strictly before the game (shift(1) before
rolling). As a canary, the same features are also computed WITH the game itself
included: a lookahead in the marts would make them agree with the canary instead.
Prints one line per feature and exits 1 on any mismatch.

Usage
  uv run python scripts/feature_lookahead_check.py               # 300 games per league
  uv run python scripts/feature_lookahead_check.py --n 1000 --seed 7

Read-only; safe while the API runs. Run after `dbt build`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
SEEDS = ROOT / "dbt" / "seeds"
TOL = 1e-6


def crosswalk(league: str, source: str) -> pd.DataFrame:
    x = pd.read_csv(SEEDS / f"{league}_team_crosswalk.csv", dtype={"source_key": str})
    return x[x.source == source]


def map_codes(df: pd.DataFrame, key: str, season: str, league: str, source: str, out: str) -> pd.DataFrame:
    """Canonical team code for a raw key, honouring the seed's season ranges."""
    x = crosswalk(league, source)
    m = df[[key, season]].drop_duplicates().merge(x, left_on=key, right_on="source_key")
    ok = (m[season] >= m.valid_from_season.fillna(0)) & (m[season] <= m.valid_to_season.fillna(9999))
    m = m[ok][[key, season, "team_code"]].rename(columns={"team_code": out})
    return df.merge(m, on=[key, season], how="left")


def rolling(df: pd.DataFrame, by: list[str], cols: list[str], window: int | None, include_current: bool) -> pd.DataFrame:
    """Sum of `cols` over the previous `window` rows (None = all previous) per group.

    Rows must already be sorted by date within each group. include_current=True
    is the lookahead canary.
    """
    keys = [df[b] for b in by]
    out = pd.DataFrame(index=df.index)
    for c in cols:
        v = df[c] if include_current else df.groupby(by, sort=False)[c].shift(1)
        grp = v.groupby(keys, sort=False)
        if window is None:
            out[c] = grp.cumsum()          # NaN stays NaN on a group's first (shifted) row
        else:
            out[c] = (grp.rolling(window, min_periods=1).sum()
                      .droplevel(list(range(len(by)))).reindex(df.index))
    return out


def compare(name: str, mart: pd.Series, mine: pd.Series, canary: pd.Series) -> bool:
    both_null = mart.isna() & mine.isna()
    diff = (mart - mine).abs()
    bad = ~both_null & ((mart.isna() != mine.isna()) | (diff > TOL))
    if canary is None:
        canary_txt = "canary n/a"
    else:
        c_same = mart.notna() & canary.notna() & ((mart - canary).abs() <= TOL)
        canary_txt = f"canary (game included) agrees on {int(c_same.sum()):4}"
    print(f"  {name:28} compared {int((~both_null).sum()):5}  mismatches {int(bad.sum()):3}"
          f"  max |diff| {diff.max():.2e}   {canary_txt}")
    if bad.any():
        print(pd.DataFrame({"mart": mart[bad], "recomputed": mine[bad]}).head(5).to_string())
    return not bad.any()


# ---------------------------------------------------------------------------
# NBA
# ---------------------------------------------------------------------------

def nba(con, n: int, seed: int) -> bool:
    raw = con.execute("select * exclude (_dlt_load_id, _dlt_id) from nba.team_game_logs").df()
    raw["game_date"] = pd.to_datetime(raw.game_date)
    opp = raw[["game_id", "team_id", "pts", "fga", "fgm", "fta", "oreb", "dreb", "tov"]].add_prefix("opp_")
    t = raw.merge(opp, left_on="game_id", right_on="opp_game_id")
    t = t[t.team_id != t.opp_team_id].copy()
    t["poss"] = 0.5 * ((t.fga - t.oreb + t.tov + 0.44 * t.fta) + (t.opp_fga - t.opp_oreb + t.opp_tov + 0.44 * t.opp_fta))
    t["fgm_adj"] = t.fgm + 0.5 * t.fg3m
    t = t.sort_values(["team_id", "season", "game_date", "game_id"]).reset_index(drop=True)
    cols = ["pts", "opp_pts", "poss", "min", "fgm_adj", "fga", "opp_oreb", "dreb"]

    feats = {}
    for tag, inc in (("ok", False), ("canary", True)):
        r10 = rolling(t, ["team_id", "season"], cols, 10, inc)
        r5 = rolling(t, ["team_id", "season"], cols, 5, inc)
        rs = rolling(t, ["team_id", "season"], cols, None, inc)
        f = pd.DataFrame({"game_id": t.game_id, "team_id": t.team_id})
        f["ortg_l10"] = 100 * r10.pts / r10.poss
        f["net_std"] = 100 * (rs.pts - rs.opp_pts) / rs.poss
        f["efg_l5"] = r5.fgm_adj / r5.fga
        f["pace_l10"] = 240 * r10.poss / r10["min"]
        f["opp_orb_pct_std"] = rs.opp_oreb / (rs.opp_oreb + rs.dreb)
        feats[tag] = f
    season_tot = t.groupby(["team_id", "season"])[["pts", "opp_pts", "poss"]].sum().reset_index()
    season_tot["net_prior"] = 100 * (season_tot.pts - season_tot.opp_pts) / season_tot.poss
    season_tot["season"] += 1
    for tag in feats:
        feats[tag] = feats[tag].merge(t[["game_id", "team_id", "season"]], on=["game_id", "team_id"])
        feats[tag] = feats[tag].merge(season_tot[["team_id", "season", "net_prior"]], on=["team_id", "season"], how="left")

    mart = con.execute("""
        select m.*, s.home_nba_team_id, s.away_nba_team_id
        from main_marts.mart_nba_game_features m
        join main_intermediate.int_nba__game_spine s using (game_key)
        where s.home_nba_team_id is not null and s.away_nba_team_id is not null""").df()
    mart = mart.sample(min(n, len(mart)), random_state=seed)
    ok = True
    print(f"\nNBA box-score features, {len(mart)} random games x home and away, from nba.team_game_logs")
    for col in ["ortg_l10", "net_std", "efg_l5", "pace_l10", "opp_orb_pct_std", "net_prior"]:
        m_all, mine_all, can_all = [], [], []
        for side in ("home", "away"):
            key = mart[["nba_game_id", f"{side}_nba_team_id", f"{side}_{col}"]].rename(
                columns={"nba_game_id": "game_id", f"{side}_nba_team_id": "team_id", f"{side}_{col}": "mart"})
            key["team_id"] = key.team_id.astype("int64")
            j = key.merge(feats["ok"][["game_id", "team_id", col]], on=["game_id", "team_id"], how="left") \
                   .merge(feats["canary"][["game_id", "team_id", col]].rename(columns={col: "canary"}),
                          on=["game_id", "team_id"], how="left")
            m_all.append(j.mart); mine_all.append(j[col]); can_all.append(j.canary)
        ok &= compare(col, pd.concat(m_all, ignore_index=True), pd.concat(mine_all, ignore_index=True),
                      None if col.endswith("_prior") else pd.concat(can_all, ignore_index=True))

    # schedule features from the raw ESPN schedule (ESPN seasons only)
    g = con.execute("""select game_id, season, cast(game_date as date) as game_date, home_id, away_id
                       from nba.games where completed and season_type in (2, 3)""").df()
    side = pd.concat([g.rename(columns={"home_id": "espn_id"})[["game_id", "season", "game_date", "espn_id"]],
                      g.rename(columns={"away_id": "espn_id"})[["game_id", "season", "game_date", "espn_id"]]])
    side = map_codes(side, "espn_id", "season", "nba", "espn_id", "team_code")
    franchise = side.groupby("game_id").team_code.count() == 2
    side = side[side.game_id.isin(franchise[franchise].index)]
    side["game_date"] = pd.to_datetime(side.game_date)
    side = side.sort_values(["team_code", "game_date", "game_id"]).reset_index(drop=True)
    prev = side.groupby("team_code").game_date.shift(1)
    prev_season = side.groupby("team_code").season.shift(1)
    gap = (side.game_date - prev).dt.days
    side["days_rest"] = np.where(prev_season == side.season, gap - 1, np.nan)
    side["is_b2b"] = ((prev_season == side.season) & (gap == 1)).astype(float)
    sm = con.execute("""select espn_game_id as game_id, home_team, away_team, home_days_rest, away_days_rest,
                               home_is_b2b::int as home_is_b2b, away_is_b2b::int as away_is_b2b,
                               home_games_last7, away_games_last7
                        from main_marts.mart_nba_game_features where espn_game_id is not null""").df()
    sm = sm.sample(min(n, len(sm)), random_state=seed)
    print(f"\nNBA schedule features, {len(sm)} random ESPN-era games x home and away, from nba.games")
    by_team = {k: v.sort_values("game_date") for k, v in side.groupby("team_code")}
    for col in ["days_rest", "is_b2b", "games_last7"]:
        m_all, mine_all = [], []
        for s in ("home", "away"):
            for r in sm.itertuples():
                tg = by_team[getattr(r, f"{s}_team")]
                row = tg[tg.game_id == r.game_id]
                if row.empty:
                    continue
                if col == "games_last7":
                    d = row.game_date.iloc[0]
                    mine = float(((d - tg.game_date).dt.days.between(1, 7)).sum())
                else:
                    mine = row[col].iloc[0]
                m_all.append(getattr(r, f"{s}_{col}")); mine_all.append(mine)
        a = pd.Series([np.nan if pd.isna(x) else float(x) for x in m_all])
        b = pd.Series([np.nan if pd.isna(x) else float(x) for x in mine_all])
        ok &= compare(col, a, b, None)
    return ok


# ---------------------------------------------------------------------------
# NHL
# ---------------------------------------------------------------------------

def nhl(con, n: int, seed: int) -> bool:
    mp = con.execute("""select gameid, playerteam, season_end, cast(game_date as date) as game_date, situation,
                               xgoalsfor, xgoalsagainst, shotattemptsfor, shotattemptsagainst, icetime
                        from nhl.moneypuck_team_games""").df()
    mp = map_codes(mp, "playerteam", "season_end", "nhl", "moneypuck", "team_code")
    wide = mp.pivot_table(index=["gameid", "team_code", "season_end", "game_date"], columns="situation",
                          values=["xgoalsfor", "xgoalsagainst", "shotattemptsfor", "shotattemptsagainst", "icetime"],
                          aggfunc="max")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    t = wide.reset_index().sort_values(["team_code", "season_end", "game_date", "gameid"]).reset_index(drop=True)
    cols = ["xgoalsfor_5on5", "xgoalsagainst_5on5", "shotattemptsfor_5on5", "shotattemptsagainst_5on5",
            "xgoalsfor_5on4", "icetime_5on4"]
    feats = {}
    for tag, inc in (("ok", False), ("canary", True)):
        r10 = rolling(t, ["team_code", "season_end"], cols, 10, inc)
        rs = rolling(t, ["team_code", "season_end"], cols, None, inc)
        f = pd.DataFrame({"gameid": t.gameid, "team_code": t.team_code})
        f["xgf_pct_5v5_l10"] = r10.xgoalsfor_5on5 / (r10.xgoalsfor_5on5 + r10.xgoalsagainst_5on5)
        f["corsi_pct_5v5_std"] = rs.shotattemptsfor_5on5 / (rs.shotattemptsfor_5on5 + rs.shotattemptsagainst_5on5)
        f["pp_xgf60_std"] = 3600 * rs.xgoalsfor_5on4 / rs.icetime_5on4
        feats[tag] = f

    gg = con.execute("""select game_id, player_id, cast(game_date as date) as game_date, team, saves, shots_against
                        from nhl.goalie_games where starter""").df()
    gg = gg.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)
    gfeat = {}
    for tag, inc in (("ok", False), ("canary", True)):
        r = rolling(gg, ["player_id"], ["saves", "shots_against"], 10, inc)
        gfeat[tag] = pd.DataFrame({"game_id": gg.game_id, "player_id": gg.player_id,
                                   "starter_sv_pct_l10": r.saves / r.shots_against})

    mart = con.execute("select * from main_marts.mart_nhl_game_features where nhl_game_id is not null").df()
    mart = mart.sample(min(n, len(mart)), random_state=seed)
    ok = True
    print(f"\nNHL features, {len(mart)} random games x home and away, from nhl.moneypuck_team_games / nhl.goalie_games")
    for col in ["xgf_pct_5v5_l10", "corsi_pct_5v5_std", "pp_xgf60_std"]:
        m_all, mine_all, can_all = [], [], []
        for side in ("home", "away"):
            key = mart[["nhl_game_id", f"{side}_team", f"{side}_{col}"]].rename(
                columns={"nhl_game_id": "gameid", f"{side}_team": "team_code", f"{side}_{col}": "mart"})
            j = key.merge(feats["ok"][["gameid", "team_code", col]], on=["gameid", "team_code"], how="left") \
                   .merge(feats["canary"][["gameid", "team_code", col]].rename(columns={col: "canary"}),
                          on=["gameid", "team_code"], how="left")
            m_all.append(j.mart); mine_all.append(j[col]); can_all.append(j.canary)
        ok &= compare(col, pd.concat(m_all, ignore_index=True), pd.concat(mine_all, ignore_index=True),
                      pd.concat(can_all, ignore_index=True))
    col = "starter_sv_pct_l10"
    m_all, mine_all, can_all = [], [], []
    for side in ("home", "away"):
        key = mart[mart[f"{side}_starter_id"].notna()][["nhl_game_id", f"{side}_starter_id", f"{side}_{col}"]].rename(
            columns={"nhl_game_id": "game_id", f"{side}_starter_id": "player_id", f"{side}_{col}": "mart"})
        key["player_id"] = key.player_id.astype("int64")
        j = key.merge(gfeat["ok"], on=["game_id", "player_id"], how="left") \
               .merge(gfeat["canary"].rename(columns={col: "canary"}), on=["game_id", "player_id"], how="left")
        m_all.append(j.mart); mine_all.append(j[col]); can_all.append(j.canary)
    ok &= compare(col, pd.concat(m_all, ignore_index=True), pd.concat(mine_all, ignore_index=True),
                  pd.concat(can_all, ignore_index=True))
    return ok


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--n", type=int, default=300, help="random games per league")
    p.add_argument("--seed", type=int, default=20261109)
    a = p.parse_args()
    con = duckdb.connect(a.db, read_only=True)
    ok = nba(con, a.n, a.seed)
    ok &= nhl(con, a.n, a.seed)
    print("\nRESULT:", "PASS - every recomputed value matches the marts" if ok else "FAIL - see mismatches above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
