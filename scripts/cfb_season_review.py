#!/usr/bin/env python3
"""
cfb_season_review.py — mid-season check of the live CFB model (read-only).

Answers two questions with the live 2026 picks:

1. Is the model performing like the backtest said it would?
   Published-pick record with 95% confidence intervals, compared with the
   backtest, plus splits by week, model-score band, favourite/underdog and
   bet type. Watch-list picks (scored but below the publish bar) are shown
   as a control group.

2. The pre-registered off_vs_preseason test
   (docs/cfb_quality/PHASE_D_FINDINGS.md, "2026 Monitoring Plan"):
   historical published picks 2021-2025 plus live 2026, split by the bet
   team's pregame off_vs_preseason (Strong > +0.15, Weak < -0.15).
   Reports the rule exactly as written, and a lift test, because the rule
   as written ("Strong covers > 60% with N > 50") is already met by the
   2021-2025 picks alone (65.5%, N=139) while Strong does no better than
   the average pick. A filter only earns its place if it adds lift.

Also re-checks every graded pick's outcome with the corrected bet-team
parser (grade_picks.backed_team_of), and lists any that were mis-graded.

Nothing is changed: read-only DuckDB, no files written unless --out.
Model changes stay a human decision (ROADMAP: agents/scripts never change
bet logic).

Usage
  python scripts/cfb_season_review.py
  python scripts/cfb_season_review.py --through-week 8
  python scripts/cfb_season_review.py --skip-history     # fast: live sections only
  python scripts/cfb_season_review.py --out data/reports/cfb_2026_wk8.md
"""

from __future__ import annotations

import argparse
import io
import math
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
BREAKEVEN = 0.524                       # -110 juice
BACKTEST_REFS = [
    ("Walk-forward v3 backtest (107-32)", 0.770),
    ("Published picks 2021-25, current scorer (Phase D, N=293)", 0.666),
]
STRONG, WEAK = 0.15, -0.15


# ── stats helpers ─────────────────────────────────────────────────────────────

def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (better than ±1.96·se at small n)."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def binom_le(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def record(df: pd.DataFrame) -> dict:
    """W-L-P, cover % excluding pushes, ROI per $1 risked, Wilson CI."""
    wins = int((df["outcome"] == "win").sum())
    losses = int((df["outcome"] == "loss").sum())
    pushes = int((df["outcome"] == "push").sum())
    n = wins + losses
    pnl = float(df["pnl"].fillna(0).sum()) if "pnl" in df else wins * 0.909 - losses
    lo, hi = wilson(wins, n)
    return {"n": n, "wins": wins, "losses": losses, "pushes": pushes,
            "cover": wins / n if n else float("nan"),
            "roi": pnl / n if n else float("nan"), "lo": lo, "hi": hi}


def fmt_row(label: str, r: dict, width: int = 34) -> str:
    if not r["n"]:
        return f"  {label:<{width}} {'—':>9}"
    wlp = f"{r['wins']}-{r['losses']}" + (f"-{r['pushes']}" if r["pushes"] else "")
    return (f"  {label:<{width}} {wlp:>9} {r['cover']*100:>6.1f}%"
            f"  [{r['lo']*100:4.0f}–{r['hi']*100:3.0f}%] {r['roi']*100:>+7.1f}%")


def header(width: int = 34) -> str:
    return (f"  {'':<{width}} {'W-L(-P)':>9} {'Cover':>7}  {'95% CI':>10} {'ROI':>8}\n"
            f"  {'-' * (width + 40)}")


def side_of(bet: str) -> str:
    m = re.search(r"\((home|away) (fav|dog)\)", bet or "")
    return f"{m.group(1)} {m.group(2)}" if m else "unknown"


def score_band(score) -> str:
    if score is None or pd.isna(score):
        return "unknown"
    s = int(score)
    return "90+" if s >= 90 else "80-89" if s >= 80 else "70-79" if s >= 70 else "<70"


def bucket(signal: float) -> str:
    return "Strong" if signal > STRONG else "Weak" if signal < WEAK else "Neutral"


# ── data ──────────────────────────────────────────────────────────────────────

def load_live(con, season: int, through_week: int | None) -> pd.DataFrame:
    df = con.execute("""
        SELECT season, week, matchup, bet, bet_type, line, model_score, n_edges,
               meets_publish_bar, outcome, pnl, home_score, away_score
        FROM cfbd.live_picks
        WHERE season = ?
    """, [season]).df()
    if through_week is not None:
        df = df[df["week"] <= through_week]
    df["graded"] = df["outcome"].isin(["win", "loss", "push"])
    df["published"] = df["meets_publish_bar"].fillna(False).astype(bool)
    return df


def regrade(df: pd.DataFrame) -> pd.DataFrame:
    """Graded picks whose stored outcome differs from a regrade with the fixed parser."""
    from grade_picks import grade_one_pick
    rows = []
    for _, p in df[df["graded"]].iterrows():
        if pd.isna(p["home_score"]) or pd.isna(p["away_score"]):
            continue
        fresh = grade_one_pick(p.to_dict(), int(p["home_score"]), int(p["away_score"]))
        if fresh["outcome"] != p["outcome"]:
            rows.append({"week": p["week"], "matchup": p["matchup"], "bet": p["bet"],
                         "stored": p["outcome"], "correct": fresh["outcome"],
                         "published": p["published"]})
    return pd.DataFrame(rows)


def live_signals(con, df: pd.DataFrame) -> pd.DataFrame:
    """Graded published 2026 picks with the bet team's pregame off_vs_preseason."""
    from grade_picks import backed_team_of
    from quality_signal_ablation import get_quality_signal
    out = []
    for _, p in df[df["graded"] & df["published"] & (df["outcome"] != "push")].iterrows():
        away, home = [s.strip() for s in p["matchup"].split(" @ ")]
        team = backed_team_of(p["bet"], home, away)
        if team is None:
            continue
        sig = get_quality_signal(con, team, int(p["season"]), int(p["week"]))
        out.append({"season": p["season"], "week": p["week"], "bet_team": team,
                    "outcome": p["outcome"], "signal": sig})
    return pd.DataFrame(out, columns=["season", "week", "bet_team", "outcome", "signal"])


def signal_table(picks: pd.DataFrame) -> dict[str, dict]:
    picks = picks[picks["signal"].notna()].copy()
    picks["bucket"] = picks["signal"].map(bucket)
    picks["pnl"] = picks["outcome"].map({"win": 0.909, "loss": -1.0})
    out = {b: record(picks[picks["bucket"] == b]) for b in ("Strong", "Neutral", "Weak")}
    out["All"] = record(picks)
    return out


def lift(t: dict[str, dict]) -> float | None:
    s, a = t["Strong"], t["All"]
    return (s["cover"] - a["cover"]) * 100 if s["n"] and a["n"] else None


# ── report ────────────────────────────────────────────────────────────────────

def report(con, season: int, through_week: int | None, skip_history: bool) -> None:
    df = load_live(con, season, through_week)
    graded = df[df["graded"]]
    last_week = int(graded["week"].max()) if len(graded) else None
    pub = graded[graded["published"]]
    watch = graded[~graded["published"]]

    print(f"CFB {season} season review — graded through week {last_week}"
          f"{f' (capped at {through_week})' if through_week else ''}")
    print(f"Picks scored: {len(df)}  ·  graded: {len(graded)}  ·  published & graded: {len(pub)}"
          f"  ·  pending: {int((~df['graded']).sum())}")

    # 1. Headline
    print("\n1. PUBLISHED PICKS vs BACKTEST")
    print(header())
    r = record(pub)
    print(fmt_row("Live published picks", r))
    print(fmt_row("Watch list (below publish bar)", record(watch)))
    if r["n"]:
        print(f"\n  Break-even at -110 is {BREAKEVEN*100:.1f}%.")
        print(f"  Chance of a record this good or better if the true rate were break-even: "
              f"{1 - binom_le(r['wins'] - 1, r['n'], BREAKEVEN):.1%}")
        for label, p in BACKTEST_REFS:
            print(f"  Chance of a record this bad or worse if the model were really "
                  f"{p*100:.1f}% [{label}]: {binom_le(r['wins'], r['n'], p):.1%}")
        print("  (Under ~5% suggests live performance genuinely differs from that reference.)")

    # 2. Splits
    if len(pub):
        print("\n2. PUBLISHED PICKS — SPLITS")
        for title, key in [("By week", lambda d: d["week"].astype(int).astype(str)),
                           ("By model score", lambda d: d["model_score"].map(score_band)),
                           ("By side", lambda d: d["bet"].map(side_of)),
                           ("By bet type", lambda d: d["bet_type"].fillna("unknown"))]:
            print(f"\n  {title}")
            print(header())
            groups = pub.assign(_k=key(pub)).groupby("_k", sort=True)
            for k, g in groups:
                print(fmt_row(str(k), record(g)))
        print("\n  Model-score bands are a calibration check: higher bands should cover more often.")

    # 3. Grading integrity
    print("\n3. GRADING CHECK (bet-team parser fix)")
    bad = regrade(df)
    if bad.empty:
        print("  ✓ Every graded pick's outcome matches a regrade with the fixed parser.")
    else:
        print(f"  ✗ {len(bad)} pick(s) were graded against the wrong team:")
        print(bad.to_string(index=False))
        print("  The records above use the stored outcomes; fix the history files and re-run.")

    # 4. Pre-registered off_vs_preseason test
    print("\n4. PRE-REGISTERED off_vs_preseason TEST (Phase D monitoring plan)")
    live = live_signals(con, df)
    tables: dict[str, dict] = {}
    if not skip_history:
        from quality_signal_ablation import historical_published_picks
        print("Recomputing 2021-2025 published picks with the current scorer (a minute or two)…",
              file=sys.stderr, flush=True)
        hist = historical_published_picks(con)
        tables["2021-2025 (backtest)"] = signal_table(hist)
        tables[f"{season} live"] = signal_table(live)
        tables["Combined"] = signal_table(pd.concat([hist[["outcome", "signal"]],
                                                     live[["outcome", "signal"]]]))
    else:
        tables[f"{season} live"] = signal_table(live)

    for name, t in tables.items():
        print(f"\n  {name}")
        print(header())
        for b in ("Strong", "Neutral", "Weak", "All"):
            label = {"Strong": "Strong (> +0.15)", "Weak": "Weak (< -0.15)",
                     "Neutral": "Neutral", "All": "All with signal"}[b]
            print(fmt_row(label, t[b]))

    print("\n  Verdict")
    if "Combined" in tables:
        c = tables["Combined"]["Strong"]
        literal = c["n"] > 50 and c["cover"] > 0.60
        print(f"  • Rule as written (Strong > 60%, N > 50, combined): "
              f"{'MET' if literal else 'not met'} — {c['cover']*100:.1f}%, N={c['n']}.")
        print("    Caveat: this was already met by 2021-2025 alone, so it can't tell a useful")
        print("    signal from a useless one.")
        lh = lift(tables["2021-2025 (backtest)"])
        ll = lift(tables[f"{season} live"])
        fmt = lambda x: "n/a" if x is None else f"{x:+.1f} pts"
        passed = lh is not None and ll is not None and lh >= 5 and ll >= 5
        print(f"  • Lift test (Strong vs all picks, ≥ +5 pts in BOTH backtest and live): "
              f"{'PASSED' if passed else 'not passed'} — backtest {fmt(lh)}, live {fmt(ll)}.")
        print(f"    Live Strong N={tables[f'{season} live']['Strong']['n']}: small, so treat any live "
              "lift as directional only.")
    else:
        print("  (history skipped — run without --skip-history for the verdict)")
    print("\n  Any change to score_game() goes through the walk-forward backtest first.")


def main() -> int:
    p = argparse.ArgumentParser(description="Mid-season review of the live CFB model (read-only).")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--through-week", type=int, default=None)
    p.add_argument("--skip-history", action="store_true",
                   help="skip the slow 2021-2025 recompute (live sections only)")
    p.add_argument("--out", type=Path, default=None, help="also save the report as Markdown")
    args = p.parse_args()

    con = duckdb.connect(DB_PATH, read_only=True)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            report(con, args.season, args.through_week, args.skip_history)
    finally:
        con.close()
    text = buf.getvalue()
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(f"```\n{text}```\n")
        print(f"\nSaved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
