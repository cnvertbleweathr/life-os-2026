"""
Goals page — full goal inventory with progress tracking.

Goal types:
  NUMERIC  — has target_numeric, current_value, shows progress bar + pace
  BINARY   — bool target (marathon_completed, promotion) — shows ✅/🔄
  MANUAL   — finance goals with no auto source — shows status + inline edit hint
  HABIT    — daily habit goals with annual target — shows pace vs expected
"""

import duckdb
import pandas as pd
import streamlit as st
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme, section_header
apply_theme()

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

st.set_page_config(page_title="Goals · ONS", page_icon="🎯", layout="wide")
st.title("🎯 Goals · 2026")

YEAR        = date.today().year
DAY_OF_YEAR = date.today().timetuple().tm_yday
DAYS_IN_YEAR = 366  # 2026 is not a leap year but habits target 366
YEAR_PCT    = DAY_OF_YEAR / DAYS_IN_YEAR  # how far through the year we are

# Clean display labels
LABELS = {
    "migrations_completed":  "Migrations Completed",
    "ps_revenue_usd":        "PS Revenue",
    "promotion":             "Director Promotion",
    "nonfiction_books_goal": "Nonfiction Books",
    "github_commits":        "GitHub Commits",
    "marathon_completed":    "Marathon Completed",
    "squat_max_lbs":         "Squat Max",
    "bodyweight_lbs_max":    "Bodyweight Max",
    "running_miles":         "Running Miles",
    "crossfit_classes":      "CrossFit Classes",
    "date_night_per_week":   "Date Nights / Week",
    "fiction_books_goal":    "Fiction Books",
    "spotify_minutes_goal":  "Spotify Minutes",
    "meditation":            "Meditation",
    "pushups_100":           "100 Pushups",
    "nonfiction_pages_10":   "10 Nonfiction Pages",
    "fiction_pages_10":      "10 Fiction Pages",
    "roth_ira":              "Roth IRA",
    "hsa":                   "HSA",
    "monthly_savings_usd":   "Monthly Savings",
}

# Goals that are binary (done / not done)
BINARY_GOALS = {"marathon_completed", "promotion", "roth_ira", "hsa"}

# Goals driven by daily habit cadence (progress vs annual pace)
HABIT_GOALS = {"meditation", "pushups_100", "nonfiction_pages_10", "fiction_pages_10"}

# Goals with no auto data source — manual only
MANUAL_GOALS = {"roth_ira", "hsa", "monthly_savings_usd",
                "migrations_completed", "ps_revenue_usd", "promotion",
                "squat_max_lbs", "bodyweight_lbs_max", "github_commits"}

# Units for display
UNITS = {
    "ps_revenue_usd":       "$",
    "monthly_savings_usd":  "$",
    "squat_max_lbs":        " lbs",
    "bodyweight_lbs_max":   " lbs",
    "running_miles":        " mi",
    "spotify_minutes_goal": " min",
}


def safe_query(sql: str) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df  = con.execute(sql).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


def fmt_value(goal_key: str, val: float) -> str:
    unit = UNITS.get(goal_key, "")
    if unit == "$":
        if val >= 1_000_000:
            return f"${val/1_000_000:.1f}M"
        if val >= 1_000:
            return f"${val/1_000:.0f}k"
        return f"${val:.0f}"
    if val == int(val):
        return f"{int(val):,}{unit}"
    return f"{val:.1f}{unit}"


def pace_status(pct: float) -> tuple[str, str]:
    """Return (label, color) based on progress vs year pace."""
    expected = YEAR_PCT * 100
    delta    = pct - expected
    if pct >= 100:
        return "✅ Complete", "#39ff6e"
    elif delta >= 5:
        return "📈 Ahead", "#39ff6e"
    elif delta >= -10:
        return "→ On pace", "#A9B2AC"
    elif delta >= -20:
        return "⚠️ At risk", "#D97706"
    else:
        return "🔴 Behind", "#e74c3c"


def render_goal_row(row: pd.Series) -> None:
    key     = str(row["goal_key"])
    label   = LABELS.get(key, key.replace("_", " ").title())
    pct     = row.get("progress_percent")
    current = row.get("current_value")
    target  = row.get("target_numeric")
    status  = str(row.get("status", "")).strip()
    vtype   = str(row.get("goal_value_type", "")).strip()
    is_bool = vtype == "bool" or key in BINARY_GOALS
    is_habit = key in HABIT_GOALS
    no_data = (current is None or pd.isna(current))
    no_pct  = (pct is None or pd.isna(pct))

    col_label, col_progress, col_status = st.columns([2, 4, 1])

    with col_label:
        manual_tag = (
            "<span style='font-size:0.6rem;color:#A9B2AC;"
            "background:#404740;padding:0.1rem 0.35rem;"
            "border-radius:3px;margin-left:0.4rem'>manual</span>"
            if key in MANUAL_GOALS else ""
        )
        habit_tag = (
            "<span style='font-size:0.6rem;color:#A9B2AC;"
            "background:#404740;padding:0.1rem 0.35rem;"
            "border-radius:3px;margin-left:0.4rem'>daily</span>"
            if is_habit else ""
        )
        st.markdown(
            f"<div style='font-size:0.85rem;font-weight:600;"
            f"color:#F5EFEB;padding:0.15rem 0'>{label}"
            f"{manual_tag}{habit_tag}</div>",
            unsafe_allow_html=True,
        )

        # Current / target underneath label
        if not no_data and target is not None and not pd.isna(target):
            cur_fmt = fmt_value(key, float(current))
            tgt_fmt = fmt_value(key, float(target))
            st.markdown(
                f"<div style='font-size:0.72rem;color:#A9B2AC'>"
                f"{cur_fmt} / {tgt_fmt}</div>",
                unsafe_allow_html=True,
            )
        elif no_data and key in MANUAL_GOALS:
            st.markdown(
                f"<div style='font-size:0.7rem;color:#A9B2AC;"
                f"font-style:italic'>No data — update goal_progress.csv</div>",
                unsafe_allow_html=True,
            )

    with col_progress:
        if is_bool:
            # Binary: done or not
            done = (
                str(current) in ("1", "1.0", "True", "true", "yes") or
                status.lower() in ("complete", "done", "completed")
            )
            st.markdown(
                f"<div style='padding:0.35rem 0;font-size:0.85rem'>"
                f"{'✅ Complete' if done else '🔄 In progress'}</div>",
                unsafe_allow_html=True,
            )
        elif not no_pct:
            pct_float = float(pct)
            capped    = min(pct_float, 100)

            if is_habit:
                # Show pace bar with expected line marker
                expected_pct = YEAR_PCT * 100
                pace_lbl, pace_clr = pace_status(pct_float)
                bar_color = pace_clr

                # Dual bar: expected (background) + actual (foreground)
                st.markdown(
                    f"<div style='position:relative;height:8px;"
                    f"background:#2C312E;border-radius:4px;margin-top:0.5rem'>"
                    # Expected pace marker
                    f"<div style='position:absolute;top:0;left:0;"
                    f"width:{expected_pct:.1f}%;height:8px;"
                    f"background:#404740;border-radius:4px'></div>"
                    # Actual progress
                    f"<div style='position:absolute;top:0;left:0;"
                    f"width:{capped:.1f}%;height:8px;"
                    f"background:{bar_color};border-radius:4px;opacity:0.9'></div>"
                    f"</div>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:0.65rem;color:#A9B2AC;margin-top:0.2rem'>"
                    f"<span>{pct_float:.0f}% complete</span>"
                    f"<span style='color:{pace_clr}'>{pace_lbl}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                # Standard numeric goal
                pace_lbl, pace_clr = pace_status(pct_float)
                bar_color = (
                    "#0B5324" if pct_float >= 80 else
                    "#D97706" if pct_float >= 40 else
                    "#e74c3c"
                )
                st.markdown(
                    f"<div style='background:#2C312E;height:6px;"
                    f"border-radius:3px;margin-top:0.5rem'>"
                    f"<div style='width:{capped:.1f}%;height:6px;"
                    f"background:{bar_color};border-radius:3px'></div></div>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:0.65rem;color:#A9B2AC;margin-top:0.2rem'>"
                    f"<span>{pct_float:.1f}%</span>"
                    f"<span style='color:{pace_clr}'>{pace_lbl}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            # No progress data at all
            st.markdown(
                f"<div style='font-size:0.75rem;color:#A9B2AC;"
                f"padding:0.3rem 0;font-style:italic'>No data</div>",
                unsafe_allow_html=True,
            )

    with col_status:
        if not no_pct and not is_bool:
            pct_float = float(pct)
            _, clr = pace_status(pct_float)
            st.markdown(
                f"<div style='text-align:right;font-size:0.8rem;"
                f"font-weight:600;color:{clr};padding:0.15rem 0'>"
                f"{min(pct_float, 100):.0f}%</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

goal_progress = safe_query("""
    SELECT domain, goal_key, goal_value_type, target_numeric,
           current_value, progress_percent, status
    FROM main_marts.mart_goal_progress
    WHERE year = 2026
    ORDER BY domain, goal_key
""")

if goal_progress is None or goal_progress.empty:
    st.caption("No goal data. Run `dbt run` after syncing pipelines.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Year progress context
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<div style='font-size:0.72rem;color:#A9B2AC;margin-bottom:0.6rem'>"
    f"Day {DAY_OF_YEAR} of {DAYS_IN_YEAR} — {YEAR_PCT*100:.1f}% through the year. "
    f"Progress bars show actual vs expected pace.</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Summary scorecard
# ─────────────────────────────────────────────────────────────────────────────

numeric_goals = goal_progress[
    goal_progress["progress_percent"].notna() &
    ~goal_progress["goal_key"].isin(BINARY_GOALS)
]
if not numeric_goals.empty:
    on_track  = (numeric_goals["progress_percent"] >= YEAR_PCT * 100 - 10).sum()
    at_risk   = ((numeric_goals["progress_percent"] < YEAR_PCT * 100 - 10) &
                 (numeric_goals["progress_percent"] >= YEAR_PCT * 100 - 25)).sum()
    behind    = (numeric_goals["progress_percent"] < YEAR_PCT * 100 - 25).sum()
    complete  = (numeric_goals["progress_percent"] >= 100).sum()
    total_n   = len(numeric_goals)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Complete",  complete,  border=True)
    c2.metric("📈 On Pace",   on_track,  border=True)
    c3.metric("⚠️ At Risk",   at_risk,   border=True)
    c4.metric("🔴 Behind",    behind,    border=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Domain filter
# ─────────────────────────────────────────────────────────────────────────────

domains = sorted(goal_progress["domain"].unique().tolist())
col_filter, _ = st.columns([2, 4])
with col_filter:
    selected = st.segmented_control(
        "Domain", ["All"] + [d.title() for d in domains], default="All"
    )

filtered = (
    goal_progress if selected == "All"
    else goal_progress[goal_progress["domain"].str.lower() == selected.lower()]
)
display_domains = (
    domains if selected == "All"
    else [selected.lower()]
)


# ─────────────────────────────────────────────────────────────────────────────
# Goals by domain
# ─────────────────────────────────────────────────────────────────────────────

for domain in display_domains:
    subset = filtered[filtered["domain"] == domain]
    if subset.empty:
        continue

    # Domain header + quick stats
    domain_numeric = subset[subset["progress_percent"].notna()]
    avg_pct = domain_numeric["progress_percent"].mean() if not domain_numeric.empty else None

    hdr_right = ""
    if avg_pct is not None:
        _, clr = pace_status(avg_pct)
        hdr_right = (
            f"<span style='font-size:0.72rem;color:{clr};"
            f"font-weight:600'>{avg_pct:.0f}% avg</span>"
        )

    st.markdown(
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:center;margin-top:1rem;margin-bottom:0.3rem'>"
        f"<div style='font-size:0.62rem;font-weight:700;letter-spacing:3px;"
        f"text-transform:uppercase;color:#A9B2AC'>{domain.upper()}</div>"
        f"{hdr_right}</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        for i, (_, row) in enumerate(subset.iterrows()):
            render_goal_row(row)
            if i < len(subset) - 1:
                st.markdown(
                    "<hr style='margin:0.3rem 0;border-color:#434A45;opacity:0.5'>",
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Finance manual update hint
# ─────────────────────────────────────────────────────────────────────────────

if selected in ("All", "Finance"):
    with st.expander("💰 Update Finance Goals", expanded=False):
        st.caption(
            "Finance goals have no automatic data source. "
            "Update `data/manual/goal_progress.csv` then run:\n"
            "```bash\npython scripts/load_goal_progress.py\ndbt run\n```"
        )
        fin = filtered[filtered["domain"] == "finance"]
        if not fin.empty:
            st.dataframe(
                fin[["goal_key", "current_value", "status", "target_numeric"]],
                hide_index=True, use_container_width=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Raw data
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("Raw data", expanded=False):
    st.dataframe(filtered, hide_index=True, use_container_width=True)
