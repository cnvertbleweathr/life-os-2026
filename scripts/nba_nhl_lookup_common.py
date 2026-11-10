"""
nba_nhl_lookup_common.py

Shared pieces for scripts/nba_pregame_lookup.py and scripts/nhl_pregame_lookup.py.
Not a script.

Everything here is computed AS OF a game date D from games strictly before D, with
the same definitions as the dbt feature models, so a lookup on a past game
reproduces that game's row in mart_{league}_game_features (the lookups check this).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
SEEDS = ROOT / "dbt" / "seeds"
K_PRIOR = 10

TIER_MARK = {"ELITE": "++", "STRONG": "+", "NEUTRAL": "=", "FADE": "-", "STRONG_FADE": "--"}


def connect(db: str | None = None):
    return duckdb.connect(str(db or DB_PATH), read_only=True)


def season_of(d: date) -> int:
    """Season = the year it ends; a season starts in September at the earliest."""
    return d.year + 1 if d.month >= 9 else d.year


def parse_date(s: str | None) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else date.today()


def resolve_team(league: str, text: str, season: int) -> str:
    """Canonical team code from a code, abbreviation or (part of) a name."""
    x = pd.read_csv(SEEDS / f"{league}_team_crosswalk.csv", dtype=str)
    t = text.strip().lower()
    codes = set(x.team_code)
    if text.upper() in codes:
        return text.upper()
    hit = x[(x.source_key.str.lower() == t) | x.source_name.str.lower().str.contains(t, regex=False)]
    found = sorted(set(hit.team_code))
    if len(found) == 1:
        return found[0]
    raise SystemExit(f"team '{text}' is ambiguous or unknown in {league}: {found or 'no match'}")


def sep(title: str) -> None:
    print(f"\n{'─' * 72}\n  {title}\n{'─' * 72}")


def fmt(v, spec: str = ".1f", none: str = "-") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return none
    return format(v, spec)


def blend(std, games, prior, k: int = K_PRIOR):
    def nan(v):
        return v is None or (isinstance(v, float) and math.isnan(v))
    if nan(std) and nan(prior):
        return None
    if nan(prior):
        return std
    if nan(std):
        return prior
    return (std * games + prior * k) / (games + k)


def haversine(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Spine-based schedule and ATS form (same definitions as macros/nba_nhl_features.sql)
# ---------------------------------------------------------------------------

def site_coords(con, league: str, venue: str | None, home_team: str, season: int):
    v = pd.read_csv(SEEDS / "nba_nhl_venues.csv")
    if venue is not None and (v.venue == venue).any():
        r = v[v.venue == venue].iloc[0]
        return float(r.lat), float(r.lng)
    c = pd.read_csv(SEEDS / "nba_nhl_team_cities.csv")
    c = c[(c.league == league) & (c.team_code == home_team)
          & (season >= c.valid_from_season.fillna(0)) & (season <= c.valid_to_season.fillna(9999))]
    return (float(c.iloc[0].lat), float(c.iloc[0].lng)) if len(c) else (None, None)


def team_games_before(con, league: str, team: str, d: date) -> pd.DataFrame:
    return con.execute(f"""
        select s.game_key, s.season, s.game_date, s.home_team, s.away_team, s.neutral_site,
               g.venue, s.home_team = ? as is_home,
               case when s.home_team = ? then s.home_ats_margin else -s.home_ats_margin end as ats_margin
        from main_intermediate.int_{league}__game_spine s
        left join main_staging.stg_{league}__games g on g.game_id = s.espn_game_id
        where ? in (s.home_team, s.away_team) and s.game_date < ?
        order by s.game_date desc, s.game_key desc
        limit 120""", [team, team, team, d]).df()


def schedule_features(con, league: str, team: str, is_home: bool, d: date, season: int,
                      site: tuple) -> dict:
    g = team_games_before(con, league, team, d)
    out = {"days_rest": None, "is_b2b": False, "is_3in4": False, "games_last7": 0,
           "road_trip_game": 0, "travel_miles": None, "ats_games_l10": 0, "ats_covers_l10": 0,
           "ats_losses_l10": 0, "ats_pushes_l10": 0, "ats_margin_avg_l10": None}
    if g.empty:
        return out
    g["game_date"] = pd.to_datetime(g.game_date).dt.date
    last = g.iloc[0]
    gap = (d - last.game_date).days
    if int(last.season) == season:
        out["days_rest"] = gap - 1
        out["is_b2b"] = gap == 1
        lat0, lng0 = site_coords(con, league, last.venue, last.home_team, int(last.season))
        if lat0 is not None and site[0] is not None:
            out["travel_miles"] = haversine(lat0, lng0, site[0], site[1])
    out["games_last7"] = int(((d - g.game_date).apply(lambda x: x.days)).between(1, 7).sum())
    out["is_3in4"] = int(((d - g.game_date).apply(lambda x: x.days)).between(1, 3).sum()) >= 2
    if not is_home:
        trip = 1
        for r in g.itertuples():
            neutral = bool(r.neutral_site) if not pd.isna(r.neutral_site) else False   # null before ESPN
            if int(r.season) != season or (r.is_home and not neutral):
                break
            trip += 1
        out["road_trip_game"] = trip
    cur = g[g.season == season].head(10)
    a = cur.ats_margin.dropna()
    out.update(ats_games_l10=len(a), ats_covers_l10=int((a > 0).sum()), ats_losses_l10=int((a < 0).sum()),
               ats_pushes_l10=int((a == 0).sum()), ats_margin_avg_l10=float(a.mean()) if len(a) else None)
    return out


def print_schedule(home: str, away: str, sh: dict, sa: dict, ats_label: str = "ATS") -> None:
    rows = [("days rest", "days_rest", "d"), ("back-to-back", "is_b2b", ""), ("3 games in 4 nights", "is_3in4", ""),
            ("games in last 7 days", "games_last7", "d"), ("road-trip game #", "road_trip_game", "d"),
            ("travel miles since last game", "travel_miles", ".0f")]
    print(f"  {'':32}{home:>10}{away:>10}")
    for label, k, spec in rows:
        hv, av = sh[k], sa[k]
        if spec == "":
            hv, av = ("yes" if hv else "no"), ("yes" if av else "no")
            print(f"  {label:32}{hv:>10}{av:>10}")
        else:
            print(f"  {label:32}{fmt(hv, spec):>10}{fmt(av, spec):>10}")
    for t, s in ((home, sh), (away, sa)):
        print(f"  {t} last {s['ats_games_l10']} {ats_label}: {s['ats_covers_l10']}-{s['ats_losses_l10']}-"
              f"{s['ats_pushes_l10']}, avg margin vs line {fmt(s['ats_margin_avg_l10'], '+.1f')}")


def print_profiles(con, league: str, home: str, away: str, season: int, ats_label: str) -> None:
    p = con.execute(f"select * from main_marts.mart_{league}_team_profiles where season = ? and team_code in (?, ?)",
                    [season, home, away]).df()
    if p.empty:
        print(f"  no profile for {season} (needs a prior season with lines)")
        return
    print(f"  window {int(p.window_from_season.iloc[0])}-{int(p.window_to_season.iloc[0])}; "
          f"descriptive only: tiers lose about the vig out of sample (docs: Phase 5)")
    for team, role in ((home, "HOME"), (away, "AWAY")):
        r = p[p.team_code == team]
        if r.empty:
            print(f"\n  {role} {team}: no profile")
            continue
        r = r.iloc[0]
        print(f"\n  [{TIER_MARK[r.tier]}] {role} {team}  tier {r.tier}")
        print(f"     {ats_label}: {int(r.ats_wins)}-{int(r.ats_losses)}-{int(r.ats_pushes)} "
              f"({fmt(r.cover_pct)}% cover, {fmt(r.ats_roi, '+.1f')}% ROI), "
              f"seasons positive {int(r.seasons_positive)}/{int(r.seasons_in_window)}")
        sits = "  ".join(f"{lab} {fmt(r[f'{k}_cover_pct'], '.0f')}% / {fmt(r[f'{k}_roi'], '+.0f')}% (n {int(r[f'{k}_games'])})"
                         for k, lab in (("home_fav", "home fav"), ("home_dog", "home dog"),
                                        ("away_fav", "away fav"), ("away_dog", "away dog")))
        print(f"     {sits}")
        print(f"     O/U: over {fmt(r.over_pct)}% (n {int(r.ou_games)}), lean {r.ou_lean}"
              + (f"; ML {fmt(r.ml_win_pct)}% won, {fmt(r.ml_roi, '+.1f')}% ROI" if league == "nhl" else ""))


def find_game(con, league: str, home: str, away: str, d: date) -> pd.Series | None:
    df = con.execute(f"select * from main_marts.mart_{league}_game_features "
                     f"where game_date = ? and home_team = ? and away_team = ?", [d, home, away]).df()
    return df.iloc[0] if len(df) else None


def check_against_mart(row: pd.Series | None, mine: dict[str, object]) -> None:
    """Compare lookup values with the mart's pregame row for the same game."""
    if row is None:
        print("\n  (no row in the feature mart for this game: upcoming game, nothing to cross-check)")
        return
    bad = []
    for col, v in mine.items():
        m = row.get(col)
        both_null = (v is None or (isinstance(v, float) and math.isnan(v))) and pd.isna(m)
        if both_null:
            continue
        if v is None or pd.isna(m) or abs(float(v) - float(m)) > 1e-6:
            bad.append(f"{col}: lookup {v} vs mart {m}")
    if bad:
        print("\n  !! lookup differs from mart_*_game_features:\n     " + "\n     ".join(bad))
    else:
        print(f"\n  cross-check: {len(mine)} lookup values match this game's row in the feature mart")


def novig_home(home_ml: float, away_ml: float) -> float:
    def imp(m):
        return -m / (-m + 100.0) if m < 0 else 100.0 / (m + 100.0)
    a, b = imp(home_ml), imp(away_ml)
    return a / (a + b)
