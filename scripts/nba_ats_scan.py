#!/usr/bin/env python3
"""
nba_ats_scan.py -- baseline ATS / totals splits on nba.historical_lines.

First-pass edge hunting, the NBA analogue of cfb_edge_validation.py:
flat -110 pricing, pushes dropped, "seasons+" = seasons with positive ROI.

  python scripts/nba_ats_scan.py
  python scripts/nba_ats_scan.py --since 2015
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "ons.duckdb"
WIN = 100 / 110


def roi(s: pd.Series) -> float:
    return float((s * WIN + (~s) * -1.0).mean() * 100)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, default=2008)
    a = p.parse_args()
    con = duckdb.connect(str(DB), read_only=True)
    d = con.execute("select * from nba.historical_lines where season >= ? and home_ats_margin <> 0",
                    [a.since]).fetchdf()
    d["home_cover"] = d.home_ats_margin > 0
    rest_diff = d.home_days_rest - d.away_days_rest

    def rep(name: str, mask: pd.Series, bet_home: bool = True) -> None:
        x = d[mask]
        s = x.home_cover if bet_home else ~x.home_cover
        by = x.assign(s=s.values).groupby("season").s.apply(roi)
        print(f"{name:<46} n={len(x):>5}  win%={s.mean()*100:5.1f}  "
              f"ROI={roi(s):+6.1f}%  seasons+ {int((by > 0).sum())}/{by.size}")

    print(f"nba.historical_lines  seasons {d.season.min()}-{d.season.max()}  games {len(d)}\n")
    rep("home ATS (all)", d.season > 0)
    rep("home favorite", d.home_spread < 0)
    rep("home dog", d.home_spread > 0)
    rep("home dog +10.5 or more", d.home_spread >= 10.5)
    rep("road fav, home on B2B", (d.home_spread > 0) & (d.home_days_rest == 1), False)
    rep("away 2+ more days rest -> bet away", rest_diff <= -2, False)
    rep("home 2+ more days rest -> bet home", rest_diff >= 2)
    rep("home B2B vs rested away -> bet away", (d.home_days_rest == 1) & (d.away_days_rest >= 2), False)

    t = d[d.total_points != d.total].dropna(subset=["total", "total_points"])
    over = t.total_points > t.total
    print(f"\ntotals: over {over.mean()*100:.1f}%  n={len(t)}")
    for b, g in t.groupby(pd.cut(t.total, [0, 200, 210, 220, 230, 240, 300]), observed=True):
        o = g.total_points > g.total
        print(f"  total {str(b):<12} n={len(g):>5}  over%={o.mean()*100:5.1f}  under ROI={roi(~o):+5.1f}%")


if __name__ == "__main__":
    main()
