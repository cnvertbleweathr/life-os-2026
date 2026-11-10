"""
nba_nhl_edges.py

Shared walk-forward engine for scripts/nba_edge_validation.py and
scripts/nhl_edge_validation.py. Not a script.

A Candidate is a betting signal with a small parameter grid (thresholds, price
bands). For every test season S the engine:
  1. scores every grid value on the seasons before S only (training),
  2. keeps the grid value with the best training ROI among those with at least
     `min_train_bets` bets; if that ROI is <= 0 it places no bets in S,
  3. bets season S with that value and records the result.
Only the season-S results (out of sample) are reported. Every grid value scored on
every training window is appended to data/betting/{league}_trials.jsonl.

Settlement (per 1-unit stake, at the price the mart carries for the chosen line):
  spread / puck line: home_ats_margin (> 0 home covers, 0 push), side price, else -110
                      (only nba historical_lines rows lack a price);
  total:              total_margin (> 0 over), over / under price, else -110;
  moneyline:          home_margin, home / away moneyline (no price -> no bet).
Pushes are counted but excluded from win% and ROI.

Bets are assumed placed at the line and price the spine chose (the close where
there is one, else the final pregame line). CLV, for 2024+ bets that have an
opening number, is how far the market moved toward the bet between open and that
line: spread / total in points, moneyline in no-vig probability.

Uncertainty: a bootstrap (2,000 resamples of the out-of-sample bets) gives the 95%
ROI interval and p_boot = share of resampled ROIs <= 0. p_adj multiplies p_boot by
the number of candidates in the run (Bonferroni).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
OUT_DIR = ROOT / "data" / "betting"
CLV_FROM_SEASON = 2024
N_BOOT = 2000


@dataclass
class Candidate:
    name: str
    family: str
    market: str                      # 'spread' | 'total' | 'ml'
    grid: list
    side: Callable[[pd.DataFrame, object], pd.Series]   # -> 'home'/'away'/'over'/'under'/None per row
    describe: str = ""
    uses_goalie: bool = False
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------

def payout(price: pd.Series) -> pd.Series:
    """Profit on a winning 1-unit bet at American odds."""
    return np.where(price < 0, 100.0 / -price, price / 100.0)


def settle(df: pd.DataFrame, side: pd.Series, market: str) -> pd.DataFrame:
    """One row per placed bet: season, game_key, side, outcome (1 win / 0 push / -1 loss), profit, clv."""
    s = side.dropna()
    s = s[s.isin(["home", "away", "over", "under"])]
    d = df.loc[s.index]
    if market == "spread":
        margin = np.where(s == "home", d.home_ats_margin, -d.home_ats_margin)
        price = np.where(s == "home", d.home_spread_price, d.away_spread_price)
        price = np.where(pd.isna(price), -110.0, price)
        ok = pd.notna(d.home_ats_margin)
    elif market == "total":
        margin = np.where(s == "over", d.total_margin, -d.total_margin)
        price = np.where(s == "over", d.over_price, d.under_price)
        price = np.where(pd.isna(price), -110.0, price)
        ok = pd.notna(d.total_margin)
    elif market == "ml":
        margin = np.where(s == "home", d.home_margin, -d.home_margin)
        price = np.where(s == "home", d.home_ml, d.away_ml)
        ok = pd.notna(d.home_margin) & pd.notna(pd.Series(price, index=d.index))
    else:
        raise ValueError(market)
    margin = pd.Series(margin, index=d.index, dtype=float)
    price = pd.Series(price, index=d.index, dtype=float)
    outcome = np.sign(margin)
    profit = np.where(outcome > 0, payout(price), np.where(outcome < 0, -1.0, 0.0))
    bets = pd.DataFrame({
        "season": d.season, "game_key": d.game_key, "side": s, "price": price,
        "outcome": outcome, "profit": profit, "clv": clv(d, s, market),
    }, index=d.index)
    return bets[ok.values & pd.notna(price).values]


def novig(ml_a: pd.Series, ml_b: pd.Series) -> pd.Series:
    def imp(m):
        return np.where(m < 0, -m / (-m + 100.0), 100.0 / (m + 100.0))
    a, b = imp(ml_a), imp(ml_b)
    return pd.Series(a / (a + b), index=ml_a.index)


def clv(d: pd.DataFrame, s: pd.Series, market: str) -> pd.Series:
    out = pd.Series(np.nan, index=d.index)
    recent = d.season >= CLV_FROM_SEASON
    if market == "spread" and "open_home_spread" in d:
        v = np.where(s == "home", d.open_home_spread - d.home_spread, d.home_spread - d.open_home_spread)
        out = pd.Series(v, index=d.index)
    elif market == "total" and "open_total" in d:
        v = np.where(s == "over", d.total - d.open_total, d.open_total - d.total)
        out = pd.Series(v, index=d.index)
    elif market == "ml" and "open_home_ml" in d:
        close_home = novig(d.home_ml, d.away_ml)
        open_home = novig(d.open_home_ml, d.open_away_ml)
        out = pd.Series(np.where(s == "home", close_home - open_home, open_home - close_home), index=d.index)
    return out.where(recent)


def summarize(bets: pd.DataFrame) -> dict:
    decided = bets[bets.outcome != 0]
    n = len(decided)
    wins = int((decided.outcome > 0).sum())
    return {
        "bets": len(bets), "decided": n, "wins": wins, "losses": n - wins,
        "pushes": int((bets.outcome == 0).sum()),
        "win_pct": 100.0 * wins / n if n else np.nan,
        "roi": 100.0 * decided.profit.sum() / n if n else np.nan,
    }


def bootstrap(profit: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    if len(profit) < 2:
        return np.nan, np.nan, np.nan
    idx = rng.integers(0, len(profit), size=(N_BOOT, len(profit)))
    rois = 100.0 * profit[idx].mean(axis=1)
    return float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5)), float((rois <= 0).mean())


# ---------------------------------------------------------------------------
# Walk forward
# ---------------------------------------------------------------------------

def walk_forward(df: pd.DataFrame, cands: list[Candidate], league: str, min_train_bets: int,
                 min_train_seasons: int, min_oos_bets: int, run_id: str, seed: int = 7
                 ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trials_path = OUT_DIR / f"{league}_trials.jsonl"
    rng = np.random.default_rng(seed)
    rows, oos_by_cand, n_trials = [], {}, 0

    with trials_path.open("a") as log:
        for c in cands:
            # settle every grid value once over all seasons
            settled = {}
            for g in c.grid:
                settled[repr(g)] = (g, settle(df, c.side(df, g), c.market))
            seasons = sorted(set().union(*[set(b.season.unique()) for _, b in settled.values()]))
            oos, chosen = [], {}
            for S in seasons:
                train_seasons = [s for s in seasons if s < S]
                if len(train_seasons) < min_train_seasons:
                    continue
                best = None
                for key, (g, b) in settled.items():
                    tr = b[b.season < S]
                    st = summarize(tr)
                    n_trials += 1
                    log.write(json.dumps({
                        "run_id": run_id, "league": league, "candidate": c.name, "family": c.family,
                        "market": c.market, "param": key, "train_seasons": [int(x) for x in train_seasons],
                        "test_season": int(S), "train_bets": st["decided"], "train_win_pct": st["win_pct"],
                        "train_roi": st["roi"],
                    }, default=float) + "\n")
                    if st["decided"] < min_train_bets or np.isnan(st["roi"]):
                        continue
                    if best is None or (st["roi"], st["decided"]) > (best[1]["roi"], best[1]["decided"]):
                        best = (key, st)
                if best is None or best[1]["roi"] <= 0:
                    chosen[int(S)] = None
                    continue
                chosen[int(S)] = best[0]
                b = settled[best[0]][1]
                oos.append(b[b.season == S].assign(param=best[0]))
            oos_df = pd.concat(oos) if oos else pd.DataFrame(columns=["season", "outcome", "profit", "clv", "param"])
            oos_by_cand[c.name] = oos_df
            st = summarize(oos_df) if len(oos_df) else summarize(pd.DataFrame({"outcome": [], "profit": []}))
            decided = oos_df[oos_df.outcome != 0] if len(oos_df) else oos_df
            lo, hi, p = bootstrap(decided.profit.to_numpy(dtype=float), rng) if len(decided) else (np.nan,) * 3
            per = (decided.groupby("season").profit.mean() * 100) if len(decided) else pd.Series(dtype=float)
            clv_s = oos_df.clv.dropna() if len(oos_df) else pd.Series(dtype=float)
            rows.append({
                "league": league, "candidate": c.name, "family": c.family, "market": c.market,
                "rule": c.describe, "uses_goalie": c.uses_goalie,
                "oos_bets": st["bets"], "wins": st["wins"], "losses": st["losses"], "pushes": st["pushes"],
                "win_pct": st["win_pct"], "roi": st["roi"], "roi_ci_lo": lo, "roi_ci_hi": hi, "p_boot": p,
                "seasons_bet": int(per.size), "seasons_pos": int((per > 0).sum()),
                "seasons_tested": len([s for s in chosen]),
                "clv_n": int(clv_s.size), "clv_avg": float(clv_s.mean()) if clv_s.size else np.nan,
                "clv_beat_pct": float(100 * (clv_s > 0).mean()) if clv_s.size else np.nan,
                "params_by_season": json.dumps(chosen),
            })
    res = pd.DataFrame(rows)
    res["p_adj"] = (res.p_boot * len(cands)).clip(upper=1.0)
    res["meets_bar"] = (
        (res.wins + res.losses) >= min_oos_bets
    ) & (res.roi > 0) & (res.roi_ci_lo > 0) & (res.p_adj < 0.05) & (res.seasons_pos >= 0.6 * res.seasons_bet)
    res["trials_this_run"] = n_trials
    res = res.sort_values(["meets_bar", "roi"], ascending=[False, False]).reset_index(drop=True)
    return res, oos_by_cand


def baselines(df: pd.DataFrame, markets: list[str]) -> None:
    """Price sanity: betting every side of a market should lose roughly the vig."""
    print("\nBaselines (every game, every season with prices; should be about -2% to -5%):")
    for m in markets:
        a, b = ("over", "under") if m == "total" else ("home", "away")
        for s in (a, b):
            st = summarize(settle(df, pd.Series(s, index=df.index), m))
            print(f"  {m:7} all {s:6} n={st['decided']:6,}  win {st['win_pct']:5.1f}%  ROI {st['roi']:+6.2f}%")


def load(league: str, db: str) -> pd.DataFrame:
    con = duckdb.connect(db, read_only=True)
    df = con.execute(f"select * from main_marts.mart_{league}_game_features").df()
    con.close()
    return df


def report(res: pd.DataFrame, oos: dict[str, pd.DataFrame], league: str, min_oos_bets: int,
           n_games: int, run_id: str, top: int = 8) -> None:
    pd.set_option("display.width", 250)
    print(f"\n{'=' * 100}\n  {league.upper()} walk-forward results (out of sample only), run {run_id}"
          f"\n  {len(res)} candidates, {int(res.trials_this_run.iloc[0])} train-window evaluations logged;"
          f" bar: n >= {min_oos_bets}, ROI CI > 0, p_adj < 0.05, >= 60% seasons positive\n{'=' * 100}")
    show = res.assign(
        n=res.wins + res.losses,
        win=res.win_pct.round(1), roi_=res.roi.round(2),
        ci=res.apply(lambda r: f"[{r.roi_ci_lo:+.1f}, {r.roi_ci_hi:+.1f}]" if pd.notna(r.roi_ci_lo) else "-", axis=1),
        seasons=res.apply(lambda r: f"{r.seasons_pos}/{r.seasons_bet}", axis=1),
        p=res.p_adj.round(3),
        clv=res.apply(lambda r: f"{r.clv_avg:+.2f} ({r.clv_beat_pct:.0f}% of {r.clv_n})" if r.clv_n else "-", axis=1),
    )
    print(show[["candidate", "market", "n", "pushes", "win", "roi_", "ci", "p", "seasons", "clv", "meets_bar"]]
          .rename(columns={"roi_": "roi%", "win": "win%", "p": "p_adj"}).to_string(index=False))
    for _, r in res.head(top).iterrows():
        o = oos[r.candidate]
        if not len(o):
            continue
        dec = o[o.outcome != 0]
        per = dec.groupby("season").agg(n=("profit", "size"), win=("outcome", lambda x: 100 * (x > 0).mean()),
                                        roi=("profit", lambda x: 100 * x.mean()), param=("param", "first"))
        print(f"\n  {r.candidate}: {r.rule}\n" + per.round(1).to_string())
    path = OUT_DIR / f"{league}_edges.csv"
    res.drop(columns=[]).to_csv(path, index=False)
    print(f"\nwrote {path.relative_to(ROOT)} ({len(res)} rows); trials appended to "
          f"data/betting/{league}_trials.jsonl; {n_games:,} games in the mart")


def new_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S")
