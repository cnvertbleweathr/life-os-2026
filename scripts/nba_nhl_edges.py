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
every training window, and every out-of-sample season, is appended to
data/betting/{league}_trials.jsonl.

Placement. A candidate is placed at the CLOSE (the line and price the spine chose:
the close where there is one, else the final pregame line) or at the OPEN (the
opening line and price, 2023-24 on with prices). An open candidate computes its
signal from the open number and settles against it; nothing from the close is used
to pick or price the bet.

Settlement (per 1-unit stake):
  spread / puck line: home_margin + line (> 0 home covers, 0 push), at the side's price;
  total:              total points - line (> 0 over), at the over / under price;
  moneyline:          home_margin, at the side's moneyline.
A missing price means no bet, except nba.historical_lines rows (no prices exist,
flat -110) and unpriced 2013-14..2016-17 NBA opens, which only ever appear in
training windows (open candidates are tested on 2023-24+, where opens are priced).
Pushes are counted but excluded from win% and ROI.

CLV. For OPEN candidates, how much better the bet's number was than the close:
spread / total in points, moneyline and NHL puck line in no-vig probability of the
bet side (close minus open). For CLOSE candidates CLV is zero by construction; the
`line_move` column instead reports how far the market moved toward the bet between
open and close (a diagnostic: negative means the signal sides against late money).

Bar (meets_bar): >= min_oos_bets decided bets, ROI > 0, bootstrap 95% ROI interval
above 0, Bonferroni p_adj < 0.05 (p_boot x every candidate and logged scan split),
at least 5 seasons with >= 20 bets, and positive in >= 60% of the seasons tested.
Candidates whose rule came from an earlier full-sample scan carry
discovered_in_sample = True: their out-of-sample numbers are optimistic.
"""

from __future__ import annotations

import json
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
OUT_DIR = ROOT / "data" / "betting"
MOVE_FROM_SEASON = 2024          # opens with prices exist from 2023-24
N_BOOT = 10000
MIN_SEASON_BETS = 20
MIN_SEASONS = 5


@dataclass
class Candidate:
    name: str
    family: str
    market: str                      # 'spread' | 'total' | 'ml'
    grid: list
    side: Callable[[pd.DataFrame, object], pd.Series]   # -> 'home'/'away'/'over'/'under'/None per row
    describe: str = ""
    placement: str = "close"         # 'close' | 'open'
    uses_goalie: bool = False
    discovered_in_sample: bool = False
    min_test_season: int = 0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------

def payout(price) -> np.ndarray:
    """Profit on a winning 1-unit bet at American odds."""
    price = np.asarray(price, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(price < 0, 100.0 / -price, price / 100.0)


def implied(m) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):   # np.where evaluates both branches
        return np.where(m < 0, -m / (-m + 100.0), 100.0 / (m + 100.0))


def novig(a, b) -> np.ndarray:
    ia, ib = implied(a), implied(b)
    return ia / (ia + ib)


def points_col(df: pd.DataFrame) -> str:
    return "total_points" if "total_points" in df else "total_goals"


def view(df: pd.DataFrame, placement: str) -> pd.DataFrame:
    """The line, prices and settlement margins for a placement."""
    if placement == "close":
        v = pd.DataFrame({
            "spread": df.home_spread, "home_sp_px": df.home_spread_price, "away_sp_px": df.away_spread_price,
            "total": df.total, "over_px": df.over_price, "under_px": df.under_price,
            "home_ml": df.home_ml, "away_ml": df.away_ml,
            "ats": df.home_ats_margin, "tot_margin": df.total_margin,
        }, index=df.index)
        flat = df.line_source.eq("historical_lines") if "line_source" in df else pd.Series(False, index=df.index)
    else:
        nan = pd.Series(np.nan, index=df.index)
        v = pd.DataFrame({
            "spread": df.open_home_spread, "home_sp_px": df.open_home_spread_price,
            "away_sp_px": df.open_away_spread_price,
            "total": df.open_total, "over_px": df.open_over_price, "under_px": df.open_under_price,
            "home_ml": df.get("open_home_ml", nan), "away_ml": df.get("open_away_ml", nan),
            "ats": df.home_margin + df.open_home_spread, "tot_margin": df[points_col(df)] - df.open_total,
        }, index=df.index)
        # 2013-14..2016-17 NBA opens (initialSpread) carry no price; training only.
        # Keyed per market on that market's own opening line.
        nba_old = (df.season < MOVE_FROM_SEASON) & ("total_points" in df)
        flat = nba_old & df.open_home_spread.notna()
        v["flat_total"] = (nba_old & df.open_total.notna()).values
        if "spread_valid" in df:   # NHL: puck-line filter applies to the open too
            v.loc[~df.spread_valid, "ats"] = np.nan
    v["flat"] = flat.values
    if "flat_total" not in v:
        v["flat_total"] = v["flat"]
    v["home_margin"] = df.home_margin
    return v


def settle(df: pd.DataFrame, side: pd.Series, market: str, placement: str = "close") -> pd.DataFrame:
    """One row per placed bet: season, game_key, side, price, outcome (1/0/-1), profit, clv, line_move."""
    s = side.dropna()
    s = s[s.isin(["home", "away", "over", "under"])]
    d, v = df.loc[s.index], view(df, placement).loc[s.index]
    home_or_over = s.isin(["home", "over"]).to_numpy()
    if market == "spread":
        margin = np.where(home_or_over, v.ats, -v.ats)
        price = np.where(home_or_over, v.home_sp_px, v.away_sp_px)
    elif market == "total":
        margin = np.where(home_or_over, v.tot_margin, -v.tot_margin)
        price = np.where(home_or_over, v.over_px, v.under_px)
    elif market == "ml":
        margin = np.where(home_or_over, v.home_margin, -v.home_margin)
        price = np.where(home_or_over, v.home_ml, v.away_ml)
    else:
        raise ValueError(market)
    price = pd.Series(price, index=d.index, dtype=float)
    if market != "ml":
        flat = v.flat_total if market == "total" else v.flat
        price = price.where(price.notna() | ~flat, -110.0)
    margin = pd.Series(margin, index=d.index, dtype=float)
    outcome = np.sign(margin)
    profit = np.where(outcome > 0, payout(price), np.where(outcome < 0, -1.0, 0.0))
    move = movement(d, s, market)
    bets = pd.DataFrame({
        "season": d.season, "season_type": d.season_type, "game_key": d.game_key, "side": s, "price": price,
        "outcome": outcome, "profit": profit,
        "clv": move if placement == "open" else np.nan,
        "line_move": move if placement == "close" else np.nan,
        "espn_line": ~v.flat if placement == "close" else True,
    }, index=d.index)
    return bets[margin.notna().values & price.notna().values]


def movement(d: pd.DataFrame, s: pd.Series, market: str) -> pd.Series:
    """How much the open number was better for the bet side than the close (2024+)."""
    home_or_over = s.isin(["home", "over"]).to_numpy()
    nhl = "total_goals" in d
    if market == "spread" and not nhl:
        v = np.where(home_or_over, d.open_home_spread - d.home_spread, d.home_spread - d.open_home_spread)
    elif market == "spread":       # NHL puck line: fixed +-1.5, compare no-vig prices
        close_h = novig(d.home_spread_price, d.away_spread_price)
        open_h = novig(d.open_home_spread_price, d.open_away_spread_price)
        same = (d.open_home_spread == d.home_spread).to_numpy()
        v = np.where(same, np.where(home_or_over, close_h - open_h, open_h - close_h), np.nan)
    elif market == "total":
        v = np.where(home_or_over, d.total - d.open_total, d.open_total - d.total)
    else:
        close_h, open_h = novig(d.home_ml, d.away_ml), novig(d.open_home_ml, d.open_away_ml)
        v = np.where(home_or_over, close_h - open_h, open_h - close_h)
    return pd.Series(v, index=d.index, dtype=float).where(d.season >= MOVE_FROM_SEASON)


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
# Trials log
# ---------------------------------------------------------------------------

def trials_path(league: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"{league}_trials.jsonl"


def log_once(league: str, key: str, records: list[dict]) -> None:
    """Append records tagged `log_key` unless that key is already in the log."""
    path = trials_path(league)
    if path.exists() and any(f'"log_key": "{key}"' in line for line in path.open()):
        return
    with path.open("a") as f:
        for r in records:
            f.write(json.dumps({**r, "log_key": key}, default=float) + "\n")


def prior_trial_count(league: str, valid_only: bool = True) -> dict:
    """Distinct (candidate, param) pairs ever tried, excluding runs marked invalid."""
    path = trials_path(league)
    if not path.exists():
        return {"pairs": 0, "runs": 0}
    rows = [json.loads(line) for line in path.open()]
    invalid = {r["run_id"] for r in rows if r.get("type") == "invalid_run"}
    good = [r for r in rows if r.get("type", "train") in ("train", "scan")
            and (not valid_only or r.get("run_id") not in invalid)]
    return {"pairs": len({(r.get("candidate"), r.get("param")) for r in good}),
            "runs": len({r.get("run_id") for r in good})}


# ---------------------------------------------------------------------------
# Walk forward
# ---------------------------------------------------------------------------

def walk_forward(df: pd.DataFrame, cands: list[Candidate], league: str, min_train_bets: int,
                 min_train_seasons: int, min_oos_bets: int, run_id: str, scan_splits: int = 0,
                 seed: int = 7) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows, oos_by_cand, n_evals = [], {}, 0

    with trials_path(league).open("a") as log:
        for c in cands:
            settled = {repr(g): (g, settle(df, c.side(df, g), c.market, c.placement)) for g in c.grid}
            seasons = sorted(set().union(*[set(b.season.unique()) for _, b in settled.values()]))
            oos, chosen = [], {}
            for S in seasons:
                train_seasons = [s for s in seasons if s < S]
                if len(train_seasons) < min_train_seasons or S < c.min_test_season:
                    continue
                best = None
                for key, (g, b) in settled.items():
                    st = summarize(b[b.season < S])
                    n_evals += 1
                    log.write(json.dumps({
                        "type": "train", "run_id": run_id, "league": league, "candidate": c.name,
                        "family": c.family, "market": c.market, "placement": c.placement, "param": key,
                        "train_seasons": [int(x) for x in train_seasons], "test_season": int(S),
                        "train_bets": st["decided"], "train_win_pct": st["win_pct"], "train_roi": st["roi"],
                    }, default=float) + "\n")
                    if st["decided"] < min_train_bets or np.isnan(st["roi"]):
                        continue
                    if best is None or (st["roi"], st["decided"]) > (best[1]["roi"], best[1]["decided"]):
                        best = (key, st)
                if best is None or best[1]["roi"] <= 0:
                    chosen[int(S)] = None
                    log.write(json.dumps({"type": "oos", "run_id": run_id, "candidate": c.name,
                                          "test_season": int(S), "param": None, "bets": 0}) + "\n")
                    continue
                chosen[int(S)] = best[0]
                b = settled[best[0]][1]
                o = b[b.season == S].assign(param=best[0])
                oos.append(o)
                so = summarize(o)
                log.write(json.dumps({"type": "oos", "run_id": run_id, "candidate": c.name,
                                      "test_season": int(S), "param": best[0], "bets": so["decided"],
                                      "win_pct": so["win_pct"], "roi": so["roi"]}, default=float) + "\n")

            cols = ["season", "season_type", "game_key", "outcome", "profit", "clv", "line_move", "espn_line", "param"]
            oos_df = pd.concat(oos) if oos else pd.DataFrame(columns=cols)
            oos_by_cand[c.name] = oos_df
            st = summarize(oos_df)
            decided = oos_df[oos_df.outcome != 0]
            # deterministic: bets in game_key order, one seed per candidate
            ordered = decided.sort_values("game_key").profit.to_numpy(dtype=float)
            lo, hi, p = bootstrap(ordered, np.random.default_rng([seed, zlib.crc32(c.name.encode())]))
            per = decided.groupby("season").profit.agg(["mean", "size"])
            counted = per[per["size"] >= MIN_SEASON_BETS]
            tested = len(chosen)
            espn = decided[decided.espn_line.astype(bool)]
            clv_s = pd.to_numeric(oos_df.clv, errors="coerce").dropna()
            mv_s = pd.to_numeric(oos_df.line_move, errors="coerce").dropna()
            rows.append({
                "league": league, "candidate": c.name, "family": c.family, "market": c.market,
                "placement": c.placement, "rule": c.describe, "uses_goalie": c.uses_goalie,
                "discovered_in_sample": c.discovered_in_sample,
                "oos_bets": st["bets"], "wins": st["wins"], "losses": st["losses"], "pushes": st["pushes"],
                "win_pct": st["win_pct"], "roi": st["roi"], "roi_ci_lo": lo, "roi_ci_hi": hi, "p_boot": p,
                "roi_espn_lines": 100 * espn.profit.mean() if len(espn) else np.nan, "n_espn_lines": len(espn),
                "seasons_tested": tested, "seasons_bet": int(per.shape[0]),
                "seasons_counted": int(counted.shape[0]), "seasons_pos": int((counted["mean"] > 0).sum()),
                "clv_n": int(clv_s.size), "clv_avg": float(clv_s.mean()) if clv_s.size else np.nan,
                "clv_beat_pct": float(100 * (clv_s > 0).mean()) if clv_s.size else np.nan,
                "line_move_n": int(mv_s.size), "line_move_avg": float(mv_s.mean()) if mv_s.size else np.nan,
                "line_move_toward_pct": float(100 * (mv_s > 0).mean()) if mv_s.size else np.nan,
                "params_by_season": json.dumps(chosen),
            })
    res = pd.DataFrame(rows)
    m = len(cands) + scan_splits
    res["p_adj"] = (res.p_boot * m).clip(upper=1.0)
    res["meets_bar"] = (
        ((res.wins + res.losses) >= min_oos_bets) & (res.roi > 0) & (res.roi_ci_lo > 0)
        & (res.p_adj < 0.05) & (res.seasons_counted >= MIN_SEASONS)
        & (res.seasons_pos >= 0.6 * res.seasons_tested)
    )
    res["bonferroni_m"] = m
    res["evals_this_run"] = n_evals
    res = res.sort_values(["meets_bar", "roi"], ascending=[False, False], na_position="last").reset_index(drop=True)
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
    hist = prior_trial_count(league)
    print(f"\n{'=' * 110}\n  {league.upper()} walk-forward results (out of sample only), run {run_id}"
          f"\n  {len(res)} candidates (+{int(res.bonferroni_m.iloc[0]) - len(res)} logged scan splits) -> Bonferroni m = "
          f"{int(res.bonferroni_m.iloc[0])}; {int(res.evals_this_run.iloc[0])} train-window evaluations this run; "
          f"{hist['pairs']} distinct candidate/param pairs logged over {hist['runs']} valid runs"
          f"\n  bar: n >= {min_oos_bets}, ROI CI > 0, p_adj < 0.05, >= {MIN_SEASONS} seasons with >= "
          f"{MIN_SEASON_BETS} bets, positive in >= 60% of seasons tested\n{'=' * 110}")

    def fmt_move(r):
        if r.placement == "open":
            return f"CLV {r.clv_avg:+.3f} ({r.clv_beat_pct:.0f}% of {r.clv_n})" if r.clv_n else "CLV -"
        return f"move {r.line_move_avg:+.3f} ({r.line_move_toward_pct:.0f}% of {r.line_move_n})" if r.line_move_n else "-"

    show = res.assign(
        n=res.wins + res.losses,
        win=res.win_pct.round(1), roi_=res.roi.round(2),
        ci=res.apply(lambda r: f"[{r.roi_ci_lo:+.1f}, {r.roi_ci_hi:+.1f}]" if pd.notna(r.roi_ci_lo) else "-", axis=1),
        seasons=res.apply(lambda r: f"{r.seasons_pos}/{r.seasons_counted} of {r.seasons_tested}", axis=1),
        p=res.p_adj.round(3),
        at=res.placement,
        clv=res.apply(fmt_move, axis=1),
        scan=res.discovered_in_sample.map({True: "yes", False: ""}),
    )
    print(show[["candidate", "market", "at", "n", "pushes", "win", "roi_", "ci", "p", "seasons", "clv", "scan", "meets_bar"]]
          .rename(columns={"roi_": "roi%", "win": "win%", "p": "p_adj", "scan": "in-sample?"}).to_string(index=False))
    print("  seasons = positive / seasons with >= 20 bets, of seasons tested. move = open->close movement toward the"
          " bet (close-placed bets; CLV is 0 there). in-sample? = rule came from an earlier full-sample scan.")
    for _, r in res.head(top).iterrows():
        o = oos[r.candidate]
        if not len(o):
            continue
        dec = o[o.outcome != 0]
        per = dec.groupby("season").agg(n=("profit", "size"), win=("outcome", lambda x: 100 * (x > 0).mean()),
                                        roi=("profit", lambda x: 100 * x.mean()), param=("param", "first"))
        extra = f"  (ESPN-priced lines only: {r.roi_espn_lines:+.2f}% on {r.n_espn_lines})" \
            if r.n_espn_lines != (r.wins + r.losses) else ""
        by_type = dec.groupby(dec.season_type.map({2: "regular", 3: "playoffs"})).agg(
            n=("profit", "size"), win=("outcome", lambda x: 100 * (x > 0).mean()),
            roi=("profit", lambda x: 100 * x.mean()))
        print(f"\n  {r.candidate} [{r.placement}]: {r.rule}{extra}\n" + per.round(1).to_string()
              + "\n  by season type:\n" + by_type.round(1).to_string())
    path = OUT_DIR / f"{league}_edges.csv"
    res.to_csv(path, index=False)
    print(f"\nwrote {path.relative_to(ROOT)} ({len(res)} rows); trials appended to "
          f"data/betting/{league}_trials.jsonl; {n_games:,} games in the mart")


def new_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S")
