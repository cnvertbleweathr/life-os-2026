"""
CFB Betting page — College football line accuracy analysis + edge finder.
Powered by CollegeFootballData.com API.
"""

import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme
apply_theme()

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

st.set_page_config(page_title="CFB Betting · ONS", page_icon="🏈", layout="wide")
st.title("🏈 CFB Betting")
st.caption("Line accuracy analysis · CollegeFootballData.com")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


# ---------------------------------------------------------------------------
# Season selector
# ---------------------------------------------------------------------------

seasons_df = safe_query("SELECT DISTINCT season FROM cfbd.lines ORDER BY season DESC")
if seasons_df is None or seasons_df.empty:
    st.caption("No CFB data yet. Run the CFBD pipeline and dbt to populate.")
    st.stop()

available_seasons = seasons_df["season"].tolist()
col_s, col_p, _ = st.columns([1, 1, 3])
with col_s:
    selected_season = st.selectbox("Season", ["All"] + [str(s) for s in available_seasons])
with col_p:
    providers_df = safe_query("SELECT DISTINCT provider FROM cfbd.lines WHERE provider IS NOT NULL ORDER BY provider")
    providers = providers_df["provider"].tolist() if providers_df is not None else []
    selected_provider = st.selectbox("Provider", ["consensus (avg)"] + providers)

season_filter = f"AND season = {selected_season}" if selected_season != "All" else ""
provider_filter = f"AND provider = '{selected_provider}'" if selected_provider != "consensus (avg)" else ""

# ---------------------------------------------------------------------------
# Top-line metrics
# ---------------------------------------------------------------------------

summary = safe_query(f"""
    SELECT
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
        sum(case when spread_push then 1 else 0 end) as spread_pushes,
        sum(case when ou_push then 1 else 0 end) as ou_pushes
    FROM main_marts.mart_cfbd_line_accuracy
    WHERE spread_result != 'unknown' AND ou_bucket != 'unknown'
    {season_filter} {provider_filter}
""")

if summary is not None and not summary.empty:
    r = summary.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Games Analyzed", f"{int(r['games']):,}", border=True)
    c2.metric("ATS Cover Rate", f"{r['ats_pct']}%",
              delta=f"{r['ats_pct'] - 50:.1f}% vs 50%",
              delta_color="normal", border=True)
    c3.metric("Over Rate", f"{r['over_pct']}%",
              delta=f"{r['over_pct'] - 50:.1f}% vs 50%",
              delta_color="normal", border=True)
    c4.metric("Avg Spread Error", f"{r['avg_margin_error']} pts", border=True)
    c5.metric("Avg O/U Error", f"{r['avg_ou_error']} pts", border=True)


# ------
# Edge factors — the money section
# ---------------------------------------------------------------------------

st.subheader("🎯 Edge Finder")
st.caption("Cover rates by situational factor — sorted by deviation from 50%")

edges = safe_query(f"""
    SELECT factor_type, factor_value, games, ats_pct, over_pct, avg_margin_vs_spread
    FROM main_marts.mart_cfbd_edge_factors
    WHERE games >= 30
    ORDER BY abs(ats_pct - 50) DESC
""")

if edges is not None and not edges.empty:
    factor_types = edges["factor_type"].unique().tolist()
    selected_factor = st.selectbox(
        "Filter by factor",
        ["All factors"] + factor_types,
    )

    display = edges if selected_factor == "All factors" else edges[edges["factor_type"] == selected_factor]

    # Color code by deviation from 50%
    display = display.copy()
    display["ats_edge"] = display["ats_pct"] - 50
    display["ou_edge"]  = display["over_pct"] - 50

    st.dataframe(
        display[["factor_type", "factor_value", "games", "ats_pct", "over_pct", "avg_margin_vs_spread"]].rename(columns={
            "factor_type":          "Factor",
            "factor_value":         "Value",
            "games":                "Games",
            "ats_pct":              "ATS Cover %",
            "over_pct":             "Over %",
            "avg_margin_vs_spread": "Avg Margin Error",
        }),
        width="stretch",
        hide_index=True,
        column_config={
            "ATS Cover %": st.column_config.ProgressColumn(
                min_value=40, max_value=65, format="%.1f%%"
            ),
            "Over %": st.column_config.ProgressColumn(
                min_value=40, max_value=65, format="%.1f%%"
            ),
        },
    )


# ------
# Cover rate by conference
# ---------------------------------------------------------------------------

st.subheader("📊 ATS Cover Rate by Conference")

conf_data = safe_query(f"""
    SELECT
        home_conference as conference,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct
    FROM main_marts.mart_cfbd_line_accuracy
    WHERE spread_result in ('covered', 'missed')
      AND home_conference IS NOT NULL
    {season_filter} {provider_filter}
    GROUP BY home_conference
    HAVING count(*) >= 30
    ORDER BY ats_pct DESC
""")

if conf_data is not None and not conf_data.empty:
    fig = go.Figure()
    colors = ["#2ecc71" if v > 50 else "#e74c3c" for v in conf_data["ats_pct"]]
    fig.add_trace(go.Bar(
        x=conf_data["conference"],
        y=conf_data["ats_pct"],
        marker_color=colors,
        hovertemplate="%{x}<br>ATS: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
    fig.update_layout(
        xaxis_title=None,
        yaxis_title="ATS Cover %",
        yaxis_range=[40, 60],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#FAFAFA"),
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
    )
    st.plotly_chart(fig, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Spread accuracy by spread size
# ---------------------------------------------------------------------------

st.subheader("📐 Accuracy vs Spread Size")

col1, col2 = st.columns(2)

spread_size = safe_query(f"""
    SELECT
        case
            when spread_abs < 3  then '0-2.5'
            when spread_abs < 7  then '3-6.5'
            when spread_abs < 10 then '7-9.5'
            when spread_abs < 14 then '10-13.5'
            when spread_abs < 21 then '14-20.5'
            else '21+'
        end as spread_bucket,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_error
    FROM main_marts.mart_cfbd_line_accuracy
    WHERE spread_result in ('covered', 'missed')
    {season_filter} {provider_filter}
    GROUP BY 1
    ORDER BY min(spread_abs)
""")

with col1:
    st.markdown("**ATS Cover % by Spread Size**")
    if spread_size is not None and not spread_size.empty:
        fig2 = go.Figure(go.Bar(
            x=spread_size["spread_bucket"],
            y=spread_size["ats_pct"],
            marker_color=["#2ecc71" if v > 50 else "#e74c3c" for v in spread_size["ats_pct"]],
            hovertemplate="%{x}<br>Cover: %{y:.1f}%<extra></extra>",
        ))
        fig2.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
        fig2.update_layout(
            yaxis_range=[40, 65],
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig2, width="stretch")

with col2:
    st.markdown("**Over % by Spread Size**")
    if spread_size is not None and not spread_size.empty:
        fig3 = go.Figure(go.Bar(
            x=spread_size["spread_bucket"],
            y=spread_size["over_pct"],
            marker_color=["#3498db" if v > 50 else "#e67e22" for v in spread_size["over_pct"]],
            hovertemplate="%{x}<br>Over: %{y:.1f}%<extra></extra>",
        ))
        fig3.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
        fig3.update_layout(
            yaxis_range=[40, 65],
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig3, width="stretch")


# ------
# Recent games with line results
# ---------------------------------------------------------------------------

st.subheader("📋 Recent Games")

recent = safe_query(f"""
    SELECT
        season,
        week,
        home_team,
        away_team,
        home_score,
        away_score,
        spread,
        over_under,
        spread_result,
        ou_bucket,
        round(margin_vs_spread, 1) as margin_vs_spread,
        round(total_vs_ou, 1) as total_vs_ou,
        home_sp_rating,
        away_sp_rating
    FROM main_marts.mart_cfbd_line_accuracy
    WHERE spread_result != 'unknown'
    {season_filter} {provider_filter}
    ORDER BY season DESC, week DESC
    LIMIT 50
""")

if recent is not None and not recent.empty:
    st.dataframe(
        recent,
        width="stretch",
        hide_index=True,
        column_config={
            "spread_result": st.column_config.TextColumn("ATS Result"),
            "ou_bucket":     st.column_config.TextColumn("O/U Result"),
        },
    )
