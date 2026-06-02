"""
Fitness page — running (Strava) + CrossFit (SugarWOD).
"""

import streamlit as st
import duckdb
import pandas as pd
import plotly.graph_objects as go
import json
import re
from datetime import date
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme, section_header
apply_theme()

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
SUGARWOD_CLEAN = ROOT / "data" / "sugarwod" / "processed" / "workouts_clean.csv"
WOD_PATH  = ROOT / "data" / "fitness" / "wod_today.json"
PH_LOGO   = ROOT / "app" / "static" / "parkhill_logo.png"

st.set_page_config(page_title="Fitness · Operating Narcisystem", page_icon="💪", layout="wide")
st.title("💪 Fitness")
st.caption("Running · CrossFit · 2026")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


def load_sugarwod() -> pd.DataFrame | None:
    if not SUGARWOD_CLEAN.exists():
        return None
    df = pd.read_csv(SUGARWOD_CLEAN)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["best_result_raw"] = pd.to_numeric(df["best_result_raw"], errors="coerce")
    df["is_pr"] = df["pr"].astype(str).str.strip().str.upper() == "PR"
    return df[df["date"].dt.year == 2026].copy()


@st.cache_data(ttl=600)
def load_wod() -> dict:
    if not WOD_PATH.exists():
        return {}
    try:
        return json.loads(WOD_PATH.read_text())
    except Exception:
        return {}


def find_similar_wods(movements: list[str], wods_df: pd.DataFrame) -> pd.DataFrame:
    """Find past SugarWOD entries that share movements with today's WOD."""
    if wods_df is None or wods_df.empty or not movements:
        return pd.DataFrame()
    pattern = "|".join(re.escape(m) for m in movements[:6])
    mask = (
        wods_df["title"].str.contains(pattern, case=False, na=False) |
        wods_df["barbell_lift"].str.contains(pattern, case=False, na=False) |
        wods_df["description"].str.contains(pattern, case=False, na=False)
    )
    return wods_df[mask].sort_values("date", ascending=False).head(5)


# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S WOD
# ─────────────────────────────────────────────────────────────────────────────

section_header("💪 Today's WOD — CrossFit Park Hill")

wod  = load_wod()
wods = load_sugarwod()

if wod.get("fetched_ok") and wod.get("text"):
    col_logo_wod, col_wod_text, col_similar = st.columns([1, 3, 2], gap="medium")

    with col_logo_wod:
        if PH_LOGO.exists():
            st.image(str(PH_LOGO), width=160)
        wod_date = wod.get("date", "")
        if wod_date != date.today().isoformat():
            st.caption(f"⚠️ Showing {wod_date}")
        else:
            st.caption(f"📅 {wod_date}")

    with col_wod_text:
        wod_text = wod["text"]
        sections = re.split(r'\b([A-Z])\.\s+', wod_text)
        if len(sections) > 1:
            i = 1
            while i < len(sections) - 1:
                letter  = sections[i]
                content = re.sub(r'https?://\S+', '', sections[i + 1]).strip()
                st.markdown(
                    f"<div style='margin:0.3rem 0;font-size:0.85rem;line-height:1.5'>"
                    f"<span style='color:#0B5324;font-weight:bold;font-size:0.9rem'>{letter}.</span> "
                    f"{content}</div>",
                    unsafe_allow_html=True,
                )
                i += 2
        else:
            clean = re.sub(r'https?://\S+', '', wod_text).strip()
            st.markdown(f"<div style='font-size:0.85rem;line-height:1.5'>{clean}</div>",
                        unsafe_allow_html=True)

    with col_similar:
        movements = wod.get("movements", [])
        if movements:
            st.caption(f"Movements: {', '.join(movements[:6])}")
        similar = find_similar_wods(movements, wods)
        if not similar.empty:
            st.markdown("**Past results — similar movements**")
            cards = []
            for _, row in similar.iterrows():
                pr_star = " ⭐" if row.get("is_pr") else ""
                result  = row.get("best_result_display", "")
                title   = row.get("title", "")
                dt      = row["date"].strftime("%b %d, %Y") if pd.notna(row["date"]) else ""
                cards.append(
                    f"<div style='background:#373D39;border-left:2px solid #0B5324;"
                    f"padding:0.3rem 0.6rem;margin:0.15rem 0;font-size:0.76rem'>"
                    f"<b>{title}</b>{pr_star}<br>"
                    f"<span style='color:#D97706'>{result}</span> "
                    f"<span style='color:#A9B2AC;font-size:0.68rem'>· {dt}</span>"
                    f"</div>"
                )
            st.markdown(
                "<div style='max-height:220px;overflow-y:auto'>"
                + "".join(cards) + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("No past results found for today's movements.")
else:
    col1, col2 = st.columns([1, 3])
    with col1:
        if PH_LOGO.exists():
            st.image(str(PH_LOGO), width=140)
    with col2:
        if wod:
            st.caption(f"WOD fetch failed: {wod.get('error', 'unknown')}")
        st.caption("Run `python scripts/fetch_wod.py` or `python scripts/daily_sync.py`.")



# ---------------------------------------------------------------------------
# Running summary
# ---------------------------------------------------------------------------

st.subheader("🏃 Running")

running = safe_query("SELECT * FROM strava.running_summary WHERE year = 2026")

if running is not None and not running.empty:
    r = running.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Miles YTD", f"{r['miles_total']:.1f}", f"goal: {r['miles_goal']:.0f}", border=True)
    c2.metric("Runs", int(r["runs_count"]), border=True)
    c3.metric("Miles/Week", f"{r['miles_per_week']:.1f}", f"need: {r['required_miles_per_week']:.1f}", border=True)
    if r.get("avg_pace_min_per_mile"):
        mins = int(r["avg_pace_min_per_mile"])
        secs = int((r["avg_pace_min_per_mile"] - mins) * 60)
        c4.metric("Avg Pace", f"{mins}:{secs:02d}/mi", border=True)
    pct = float(r["miles_progress_pct"])
    st.progress(min(int(pct), 100), text=f"{pct:.1f}% of annual goal")
else:
    st.caption("No running data. Run `python run_pipelines.py --only strava`.")

# Weekly mileage — all weeks including zeros
weekly = safe_query("""
    WITH all_weeks AS (
        SELECT strftime(range::date, '%Y-W%W') as week
        FROM range(DATE '2026-01-01', current_date + INTERVAL 1 DAY, INTERVAL 1 WEEK)
    ),
    run_weeks AS (
        SELECT strftime(start_date::date, '%Y-W%W') as week,
               sum(distance_miles) as miles
        FROM strava.activities
        WHERE is_run = true AND year = 2026
        GROUP BY week
    )
    SELECT a.week, coalesce(r.miles, 0) as miles
    FROM all_weeks a
    LEFT JOIN run_weeks r ON a.week = r.week
    ORDER BY a.week
""")

if weekly is not None and not weekly.empty:
    st.markdown("**Weekly Miles**")
    st.bar_chart(weekly.set_index("week")["miles"], width="stretch")

recent_runs = safe_query("""
    SELECT
        start_date::date as date,
        name,
        round(distance_miles, 2) as miles,
        printf('%d:%02d', cast(moving_time_s/60 as int), cast(moving_time_s%60 as int)) as duration,
        round(moving_time_s / 60.0 / nullif(distance_miles, 0), 2) as pace_min_per_mile
    FROM strava.activities
    WHERE is_run = true AND year = 2026
    ORDER BY start_date DESC
    LIMIT 10
""")

if recent_runs is not None and not recent_runs.empty:
    st.markdown("**Recent Runs**")
    st.dataframe(recent_runs, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# CrossFit / SugarWOD
# ---------------------------------------------------------------------------

st.subheader("🏋️ CrossFit")

wods = load_sugarwod()

if wods is None:
    st.caption("No CrossFit data. Run `python scripts/import_sugarwod_csv.py --input /path/to/workouts.csv`.")
    st.stop()

# ---------------------------------------------------------------------------
# Top-line metrics
# ---------------------------------------------------------------------------

total_classes = wods["date"].nunique()
total_prs = wods["is_pr"].sum()
rx_count = (wods["rx_or_scaled"].str.upper() == "RX").sum()
rx_rate = round(rx_count / len(wods) * 100, 1) if len(wods) else 0
goal_classes = 160

c1, c2, c3, c4 = st.columns(4)
c1.metric("Classes YTD", total_classes, f"goal: {goal_classes}", border=True)
c2.metric("Progress", f"{round(total_classes / goal_classes * 100, 1)}%", border=True)
c3.metric("PRs Set", int(total_prs), border=True)
c4.metric("RX Rate", f"{rx_rate}%", border=True)

st.progress(min(int(total_classes / goal_classes * 100), 100))

# ---------------------------------------------------------------------------
# Attendance — classes per week
# ---------------------------------------------------------------------------

st.subheader("Classes per week")


wods["week"] = wods["date"].dt.strftime("%Y-W%W")
classes_per_week = (
    wods.groupby("week")["date"]
    .nunique()
    .reset_index()
    .rename(columns={"date": "classes"})
    .sort_values("week")
)

# Fill in zero weeks
all_weeks = pd.date_range("2026-01-01", pd.Timestamp.today(), freq="W-MON")
all_week_labels = [d.strftime("%Y-W%W") for d in all_weeks]
full_weeks = pd.DataFrame({"week": all_week_labels})
classes_per_week = full_weeks.merge(classes_per_week, on="week", how="left").fillna(0)
classes_per_week["classes"] = classes_per_week["classes"].astype(int)

st.bar_chart(classes_per_week.set_index("week")["classes"], width="stretch")

# ---------------------------------------------------------------------------
# Lift progressions
# ---------------------------------------------------------------------------

st.subheader("Lift progressions")


lifts_df = wods[
    (wods["score_type"] == "Load") &
    wods["barbell_lift"].notna() &
    (wods["barbell_lift"].str.strip() != "")
].copy()

if not lifts_df.empty:
    available_lifts = sorted(lifts_df["barbell_lift"].unique())
    selected_lifts = st.multiselect(
        "Select lifts to compare",
        options=available_lifts,
        default=[l for l in ["Front Squat", "Back Squat", "Clean & Jerk"] if l in available_lifts],
    )

    if selected_lifts:
        fig = go.Figure()

        colors = [
            "#4FC3F7", "#81C784", "#FFB74D", "#F06292",
            "#CE93D8", "#80DEEA", "#FFCC02", "#FF8A65",
        ]

        for i, lift in enumerate(selected_lifts):
            subset = lifts_df[lifts_df["barbell_lift"] == lift].sort_values("date")
            color = colors[i % len(colors)]

            fig.add_trace(go.Scatter(
                x=subset["date"],
                y=subset["best_result_raw"],
                mode="lines+markers",
                name=lift,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                hovertemplate=f"<b>{lift}</b><br>%{{x|%b %d}}<br>%{{y}} lbs<extra></extra>",
            ))

            prs = subset[subset["is_pr"]]
            if not prs.empty:
                fig.add_trace(go.Scatter(
                    x=prs["date"],
                    y=prs["best_result_raw"],
                    mode="markers",
                    name=f"{lift} PR",
                    marker=dict(
                        size=14,
                        color=color,
                        symbol="star",
                        line=dict(color="white", width=1),
                    ),
                    hovertemplate=f"<b>⭐ PR — {lift}</b><br>%{{x|%b %d}}<br>%{{y}} lbs<extra></extra>",
                    showlegend=False,
                ))

        fig.update_layout(
            xaxis_title=None,
            yaxis_title="Weight (lbs)",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            hovermode="x unified",
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )

        st.plotly_chart(fig, width="stretch")

        lift_maxes = (
            lifts_df[lifts_df["barbell_lift"].isin(selected_lifts)]
            .groupby("barbell_lift")["best_result_raw"]
            .agg(["max", "min", "count"])
            .reset_index()
            .rename(columns={
                "barbell_lift": "Lift",
                "max": "Best (lbs)",
                "min": "First (lbs)",
                "count": "Sessions",
            })
            .sort_values("Best (lbs)", ascending=False)
        )
        st.dataframe(lift_maxes, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# PR log
# ---------------------------------------------------------------------------

st.subheader("PR log · 2026")


prs = wods[wods["is_pr"]].sort_values("date", ascending=False)[
    ["date", "title", "barbell_lift", "best_result_display", "rx_or_scaled"]
].rename(columns={
    "date": "Date",
    "title": "Workout",
    "barbell_lift": "Lift",
    "best_result_display": "Result",
    "rx_or_scaled": "RX/Scaled",
})

if not prs.empty:
    st.dataframe(prs, width="stretch", hide_index=True)