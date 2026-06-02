"""
CFB Betting page — three tabs:
  1. Edge Matrix   — situational factors ranked by exploitability
  2. Team Intel    — team card with opponent matchup + spread analysis
  3. Line Accuracy — historical spread/OU accuracy (original dashboard)
"""

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme, section_header
apply_theme()

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

st.set_page_config(page_title="CFB Betting · ONS", page_icon="🏈", layout="wide")
st.title("🏈 CFB Betting")
st.caption("Line accuracy · Edge matrix · Team intelligence · CollegeFootballData.com")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df  = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Guard — no data yet
# ─────────────────────────────────────────────────────────────────────────────

seasons_df = safe_query("SELECT DISTINCT season FROM cfbd.lines ORDER BY season DESC")
if seasons_df is None or seasons_df.empty:
    st.info(
        "No CFB data yet. Run the CFBD pipeline and dbt to populate.\n\n"
        "```bash\n"
        "python pipelines/cfbd_pipeline.py --year 2021 --end-year 2025 --skip-advanced\n"
        "dbt run --profiles-dir dbt/profiles --project-dir dbt\n"
        "```"
    )
    st.stop()

available_seasons = seasons_df["season"].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_matrix, tab_team, tab_accuracy = st.tabs([
    "📊 Edge Matrix",
    "🔍 Team Intel",
    "📐 Line Accuracy",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — EDGE MATRIX
# ═════════════════════════════════════════════════════════════════════════════

with tab_matrix:
    st.subheader("Situational Edge Matrix")
    st.caption(
        "Every testable condition ranked by ATS cover rate deviation from 50%. "
        "Higher absolute edge = more exploitable. Filter by min sample size and category."
    )

    col_min, col_cat, col_sort = st.columns([1, 2, 2])
    with col_min:
        min_games = st.number_input("Min games", min_value=10, max_value=200,
                                    value=30, step=10)
    with col_cat:
        cat_options = ["All categories"]
        edges_raw = safe_query("SELECT DISTINCT factor_type FROM main_marts.mart_cfbd_edge_factors ORDER BY factor_type")
        if edges_raw is not None:
            cat_options += edges_raw["factor_type"].tolist()
        selected_cat = st.selectbox("Category", cat_options)
    with col_sort:
        sort_by = st.segmented_control(
            "Sort by", ["ATS Edge", "Over Edge", "Sample Size"], default="ATS Edge"
        )

    cat_filter = "" if selected_cat == "All categories" else f"AND factor_type = '{selected_cat}'"
    sort_col = {
        "ATS Edge":    "abs(ats_pct - 50) DESC",
        "Over Edge":   "abs(over_pct - 50) DESC",
        "Sample Size": "games DESC",
    }[sort_by]

    edges = safe_query(f"""
        SELECT
            factor_type     AS "Category",
            factor_value    AS "Condition",
            games           AS "Games",
            round(ats_pct, 1)              AS "ATS Cover %",
            round(ats_pct - 50, 1)         AS "ATS Edge",
            round(over_pct, 1)             AS "Over %",
            round(over_pct - 50, 1)        AS "O/U Edge",
            round(avg_margin_vs_spread, 1) AS "Avg Margin Error"
        FROM main_marts.mart_cfbd_edge_factors
        WHERE games >= {min_games} {cat_filter}
        ORDER BY {sort_col}
    """)

    if edges is not None and not edges.empty:
        # Summary callouts
        best_ats   = edges.loc[edges["ATS Edge"].abs().idxmax()]
        best_ou    = edges.loc[edges["O/U Edge"].abs().idxmax()]
        biggest    = edges.loc[edges["Games"].idxmax()]

        c1, c2, c3 = st.columns(3)
        with c1:
            with st.container(border=True):
                st.caption("STRONGEST ATS EDGE")
                st.markdown(f"**{best_ats['Condition']}**")
                color = "#39ff6e" if best_ats["ATS Edge"] > 0 else "#e74c3c"
                st.markdown(
                    f"<span style='color:{color};font-size:1.3rem;font-weight:bold'>"
                    f"{best_ats['ATS Cover %']}% cover</span> "
                    f"<span style='color:#a09880'>({best_ats['Games']} games)</span>",
                    unsafe_allow_html=True,
                )
        with c2:
            with st.container(border=True):
                st.caption("STRONGEST O/U EDGE")
                st.markdown(f"**{best_ou['Condition']}**")
                color = "#39ff6e" if best_ou["O/U Edge"] > 0 else "#e74c3c"
                st.markdown(
                    f"<span style='color:{color};font-size:1.3rem;font-weight:bold'>"
                    f"{best_ou['Over %']}% overs</span> "
                    f"<span style='color:#a09880'>({best_ou['Games']} games)</span>",
                    unsafe_allow_html=True,
                )
        with c3:
            with st.container(border=True):
                st.caption("LARGEST SAMPLE")
                st.markdown(f"**{biggest['Condition']}**")
                st.markdown(
                    f"<span style='color:#4db8d4;font-size:1.3rem;font-weight:bold'>"
                    f"{biggest['Games']:,} games</span> "
                    f"<span style='color:#a09880'>{biggest['ATS Cover %']}% cover</span>",
                    unsafe_allow_html=True,
                )

        st.space("small")

        # Full sortable table
        st.dataframe(
            edges,
            hide_index=True,
            column_config={
                "ATS Cover %": st.column_config.ProgressColumn(
                    min_value=40, max_value=65, format="%.1f%%"
                ),
                "Over %": st.column_config.ProgressColumn(
                    min_value=40, max_value=65, format="%.1f%%"
                ),
                "ATS Edge": st.column_config.NumberColumn(format="%.1f"),
                "O/U Edge": st.column_config.NumberColumn(format="%.1f"),
            },
        )

        # ATS edge waterfall chart
        st.subheader("ATS Edge by Condition")
        edges["_abs_edge"] = edges["ATS Edge"].abs()
        top_edges = edges.nlargest(20, "_abs_edge").drop(columns=["_abs_edge"])
        edges = edges.drop(columns=["_abs_edge"])
        colors = ["#39ff6e" if v > 0 else "#e74c3c" for v in top_edges["ATS Edge"]]
        fig = go.Figure(go.Bar(
            x=top_edges["Condition"],
            y=top_edges["ATS Edge"],
            marker_color=colors,
            hovertemplate="%{x}<br>Edge: %{y:+.1f}%<extra></extra>",
        ))
        fig.add_hline(y=0, line_color="white", opacity=0.4)
        fig.update_layout(
            xaxis_title=None, yaxis_title="ATS Edge vs 50%",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=10, b=0), height=320,
            xaxis=dict(tickangle=-35, gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig)

    else:
        st.caption("No edge data. Run dbt to build mart_cfbd_edge_factors.")

    # Extended edges
    st.subheader("Extended Situational Edges")
    st.caption("Weather, PPA gap, returning production, talent, home defense — extended factor analysis")

    ext = safe_query(f"""
        SELECT
            factor_type     AS "Category",
            factor_value    AS "Condition",
            games           AS "Games",
            round(ats_pct, 1)       AS "ATS Cover %",
            round(ats_pct - 50, 1)  AS "ATS Edge",
            round(over_pct, 1)      AS "Over %",
            round(over_pct - 50, 1) AS "O/U Edge"
        FROM main_marts.mart_cfbd_extended_edges
        WHERE games >= {min_games} {cat_filter}
        ORDER BY {sort_col}
    """)

    if ext is not None and not ext.empty:
        st.dataframe(
            ext, hide_index=True,
            column_config={
                "ATS Cover %": st.column_config.ProgressColumn(
                    min_value=35, max_value=75, format="%.1f%%"
                ),
                "Over %": st.column_config.ProgressColumn(
                    min_value=35, max_value=75, format="%.1f%%"
                ),
            },
        )
    else:
        st.caption("No extended edge data. Run cfbd_extended_pipeline then dbt.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — TEAM INTEL
# ═════════════════════════════════════════════════════════════════════════════

with tab_team:

    # ── Team selectors ────────────────────────────────────────────────────────
    teams_df = safe_query("""
        SELECT DISTINCT team, conference, tier
        FROM cfbd.team_profiles
        ORDER BY team
    """)

    if teams_df is None or teams_df.empty:
        st.caption("No team profiles. Run cfb_build_team_profiles.py.")
        st.stop()

    all_teams = teams_df["team"].tolist()

    col_t1, col_t2, col_spread_sel = st.columns([2, 2, 1])

    with col_t1:
        primary_team = st.selectbox(
            "Primary team", all_teams,
            index=all_teams.index("Ohio State") if "Ohio State" in all_teams else 0,
            key="primary_team"
        )

    with col_t2:
        opponent_options = ["— No opponent —"] + [t for t in all_teams if t != primary_team]
        opponent = st.selectbox("Opponent (optional)", opponent_options, key="opponent")
        opponent = None if opponent == "— No opponent —" else opponent

    with col_spread_sel:
        if opponent:
            spread_options = [
                "-21", "-17", "-14", "-10", "-7", "-6", "-5", "-4", "-3",
                "PK", "+3", "+4", "+5", "+6", "+7", "+10", "+14", "+17", "+21"
            ]
            spread_val = st.selectbox(
                f"{primary_team} spread", spread_options,
                index=spread_options.index("-7"),
                key="spread_val"
            )
        else:
            spread_val = None

    st.divider()

    # ── Load primary team profile ─────────────────────────────────────────────
    profile = safe_query(f"""
        SELECT * FROM cfbd.team_profiles WHERE team = '{primary_team}'
    """)

    if profile is None or profile.empty:
        st.caption(f"No profile data for {primary_team}.")
        st.stop()

    p = profile.iloc[0]

    # Tier badge colors
    tier_colors = {
        "ELITE":       "#39ff6e",
        "STRONG":      "#4db8d4",
        "NEUTRAL":     "#a09880",
        "FADE":        "#e67e22",
        "STRONG_FADE": "#e74c3c",
    }
    tier       = str(p.get("tier", "NEUTRAL"))
    tier_color = tier_colors.get(tier, "#a09880")

    # ── Primary team card ──────────────────────────────────────────────────────
    col_card, col_situations, col_trend = st.columns([2, 2, 2], gap="medium")

    with col_card:
        st.markdown(
            f"<div style='background:#0a2a36;border:1px solid rgba(77,184,212,0.2);"
            f"border-top:3px solid {tier_color};padding:1rem 1.2rem;'>"
            f"<div style='font-family:Alfa Slab One,serif;font-size:1.4rem;"
            f"color:#e8dcc8'>{primary_team}</div>"
            f"<div style='color:#a09880;font-size:0.75rem;letter-spacing:2px;"
            f"text-transform:uppercase;margin:0.2rem 0'>{p.get('conference','')}</div>"
            f"<div style='display:inline-block;background:{tier_color}22;"
            f"border:1px solid {tier_color};color:{tier_color};"
            f"font-size:0.65rem;letter-spacing:3px;padding:0.15rem 0.5rem;"
            f"margin-bottom:0.8rem'>{tier}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.space("small")

        # Core metrics
        roi        = float(p.get("total_roi", 0))
        win_pct    = float(p.get("total_win_pct", 0))  # already stored as percentage
        prof_szns  = int(p.get("profitable_seasons", 0))
        total_g    = int(p.get("total_games", 0))
        home_roi   = float(p.get("home_roi", 0))
        away_roi   = float(p.get("away_roi", 0))
        home_fav   = float(p.get("home_fav_roi", 0))
        home_dog   = float(p.get("home_dog_roi", 0))
        away_fav   = float(p.get("away_fav_roi", 0))
        away_dog   = float(p.get("away_dog_roi", 0))
        ppa_roi    = float(p.get("home_ppa_roi", 0))
        over_home  = float(p.get("home_over_pct", 0))
        over_away  = float(p.get("away_over_pct", 0))

        roi_color = "#39ff6e" if roi > 0 else "#e74c3c"

        c1, c2 = st.columns(2)
        c1.metric("Overall ROI", f"{roi:+.1f}%", border=True)
        c2.metric("ATS Win %", f"{win_pct:.1f}%", border=True)
        c1.metric("Profitable Seasons", f"{prof_szns}/5", border=True)
        c2.metric("Games in Sample", total_g, border=True)

        st.space("small")
        st.markdown("**O/U Lean**")
        ou_col1, ou_col2 = st.columns(2)
        ou_col1.metric("Home Over %", f"{over_home:.1f}%", border=True)
        ou_col2.metric("Away Over %", f"{over_away:.1f}%", border=True)

        best_sit  = str(p.get("best_situation", ""))
        worst_sit = str(p.get("worst_situation", ""))
        best_roi  = float(p.get("best_situation_roi", 0))
        worst_roi = float(p.get("worst_situation_roi", 0))

        if best_sit:
            st.success(f"✅ **Best:** {best_sit.replace('_',' ').title()} ({best_roi:+.1f}% ROI)",
                       icon=":material/trending_up:")
        if worst_sit:
            st.error(f"❌ **Avoid:** {worst_sit.replace('_',' ').title()} ({worst_roi:+.1f}% ROI)",
                     icon=":material/trending_down:")

    with col_situations:
        st.markdown("**Situational ROI Breakdown**")

        situations = {
            "Home (all)":    home_roi,
            "Home favorite": home_fav,
            "Home underdog": home_dog,
            "Away (all)":    away_roi,
            "Away favorite": away_fav,
            "Away underdog": away_dog,
            "PPA edge (home)": ppa_roi,
        }

        sit_df = pd.DataFrame([
            {"Situation": k, "ROI": v}
            for k, v in situations.items()
        ])

        colors = ["#39ff6e" if v >= 0 else "#e74c3c" for v in sit_df["ROI"]]
        fig_sit = go.Figure(go.Bar(
            y=sit_df["Situation"],
            x=sit_df["ROI"],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}<br>ROI: %{x:+.1f}%<extra></extra>",
            text=[f"{v:+.1f}%" for v in sit_df["ROI"]],
            textposition="outside",
        ))
        fig_sit.add_vline(x=0, line_color="white", opacity=0.4)
        fig_sit.update_layout(
            xaxis_title="ROI %", yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA", size=11),
            margin=dict(l=0, r=60, t=10, b=0), height=320,
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig_sit)

        # Betting rules derived from profile
        st.markdown("**Betting rules for this team:**")
        rules = []
        if home_dog > 20:
            rules.append(f"✅ Bet home underdog ({home_dog:+.1f}% ROI)")
        if away_dog > 20:
            rules.append(f"✅ Bet away underdog ({away_dog:+.1f}% ROI)")
        if home_fav > 15:
            rules.append(f"✅ Lean home favorite ({home_fav:+.1f}% ROI)")
        if away_fav > 15:
            rules.append(f"✅ Lean away favorite ({away_fav:+.1f}% ROI)")
        if home_fav < -20:
            rules.append(f"❌ Never bet home favorite ({home_fav:+.1f}% ROI)")
        if away_dog < -20:
            rules.append(f"❌ Never bet away underdog ({away_dog:+.1f}% ROI)")
        if ppa_roi > 20:
            rules.append(f"✅ Strong PPA edge situations ({ppa_roi:+.1f}% ROI)")
        if over_home > 65:
            rules.append(f"📈 Lean OVER at home ({over_home:.1f}% overs)")
        if over_home < 40:
            rules.append(f"📉 Lean UNDER at home ({over_home:.1f}% overs)")
        if over_away < 40:
            rules.append(f"📉 Lean UNDER away ({over_away:.1f}% overs)")

        # Fade conditions (bet AGAINST)
        fade_rules = []
        if home_fav < -20:
            fade_rules.append(f"🚫 Fade as home favorite ({home_fav:+.1f}% ROI)")
        if away_dog < -20:
            fade_rules.append(f"🚫 Fade as away underdog ({away_dog:+.1f}% ROI)")
        if away_fav < -20:
            fade_rules.append(f"🚫 Fade as away favorite ({away_fav:+.1f}% ROI)")
        if home_dog < -20:
            fade_rules.append(f"🚫 Fade as home underdog ({home_dog:+.1f}% ROI)")
        if ppa_roi < -20:
            fade_rules.append(f"🚫 Fade in PPA edge situations ({ppa_roi:+.1f}% ROI)")

        all_rules = rules + fade_rules
        if all_rules:
            for rule in all_rules:
                color = "#e74c3c" if "🚫" in rule else "#e8dcc8"
                st.markdown(
                    f"<div style='font-size:0.78rem;padding:0.2rem 0;"
                    f"color:{color}'>{rule}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No strong directional rules — NEUTRAL tier, bet situational factors.")

    with col_trend:
        st.markdown("**Season-by-season ROI trend**")

        try:
            import json
            season_rois_raw = p.get("season_rois_json", "[]")
            season_rois = json.loads(season_rois_raw) if season_rois_raw else []
            if season_rois:
                srdf = pd.DataFrame(season_rois)
                colors_trend = ["#39ff6e" if v >= 0 else "#e74c3c"
                                for v in srdf["roi"]]
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Bar(
                    x=srdf["season"].astype(str),
                    y=srdf["roi"],
                    marker_color=colors_trend,
                    hovertemplate="Season %{x}<br>ROI: %{y:+.1f}%<extra></extra>",
                ))
                fig_trend.add_hline(y=0, line_color="white", opacity=0.3,
                                    line_dash="dash")
                fig_trend.update_layout(
                    xaxis_title=None, yaxis_title="ROI %",
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#FAFAFA"),
                    margin=dict(l=0, r=0, t=10, b=0), height=220,
                    yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
                )
                st.plotly_chart(fig_trend)

                # Trend direction
                if len(srdf) >= 3:
                    recent_avg = srdf["roi"].tail(2).mean()
                    early_avg  = srdf["roi"].head(2).mean()
                    if recent_avg > early_avg + 5:
                        st.success("📈 Trending up — edge strengthening", icon=":material/trending_up:")
                    elif recent_avg < early_avg - 5:
                        st.warning("📉 Trending down — fading edge", icon=":material/trending_down:")
                    else:
                        st.caption("→ Consistent — no strong trend")
            else:
                st.caption("No season breakdown available.")
        except Exception as e:
            st.caption(f"Season trend unavailable: {e}")

        # SP+ and advanced stats for most recent season
        st.markdown("**Latest season efficiency (SP+ & PPA)**")
        latest_season = max(available_seasons)
        sp = safe_query(f"""
            SELECT rating, offense, defense
            FROM cfbd.sp_ratings
            WHERE team = '{primary_team}' AND season = {latest_season}
        """)
        adv = safe_query(f"""
            SELECT off_ppa, def_ppa, off_success_rate, def_havoc_total
            FROM cfbd.advanced_stats
            WHERE team = '{primary_team}' AND season = {latest_season}
        """)

        if sp is not None and not sp.empty:
            s = sp.iloc[0]
            sa, sb, sc = st.columns(3)
            sa.metric("SP+ Overall", f"{float(s['rating']):.1f}", border=True)
            sb.metric("SP+ Off", f"{float(s['offense']):.1f}", border=True)
            sc.metric("SP+ Def", f"{float(s['defense']):.1f}", border=True)

        if adv is not None and not adv.empty:
            a = adv.iloc[0]
            aa, ab = st.columns(2)
            aa.metric("Off PPA", f"{float(a['off_ppa']):.3f}", border=True)
            ab.metric("Def PPA", f"{float(a['def_ppa']):.3f}", border=True)
            ac, ad = st.columns(2)
            ac.metric("Success Rate", f"{float(a['off_success_rate']):.1%}", border=True)
            ad.metric("Def Havoc", f"{float(a['def_havoc_total']):.3f}", border=True)

    # ── Matchup analysis (opponent selected) ──────────────────────────────────
    if opponent:
        st.divider()
        st.subheader(f"⚔️ Matchup: {primary_team} vs {opponent}")

        opp_profile = safe_query(f"""
            SELECT * FROM cfbd.team_profiles WHERE team = '{opponent}'
        """)

        is_pk          = spread_val == "PK"
        spread_numeric = 0.0 if is_pk else float(spread_val.replace("+", ""))
        primary_is_fav = spread_numeric < 0
        primary_is_dog = spread_numeric > 0
        abs_spread     = abs(spread_numeric)
        latest         = max(available_seasons)

        # SP+ and advanced stats for both teams
        both_sp = safe_query(f"""
            SELECT team, rating, offense, defense
            FROM cfbd.sp_ratings
            WHERE team IN ('{primary_team}', '{opponent}') AND season = {latest}
        """)
        both_adv = safe_query(f"""
            SELECT team, off_ppa, def_ppa, off_success_rate, def_success_rate,
                   def_havoc_total, off_rush_ppa, def_rush_success_rate
            FROM cfbd.advanced_stats
            WHERE team IN ('{primary_team}', '{opponent}') AND season = {latest}
        """)

        prim_sp  = both_sp[both_sp["team"] == primary_team].iloc[0]  if both_sp  is not None and not both_sp[both_sp["team"] == primary_team].empty  else None
        opp_sp   = both_sp[both_sp["team"] == opponent].iloc[0]       if both_sp  is not None and not both_sp[both_sp["team"] == opponent].empty       else None
        prim_adv = both_adv[both_adv["team"] == primary_team].iloc[0] if both_adv is not None and not both_adv[both_adv["team"] == primary_team].empty else None
        opp_adv  = both_adv[both_adv["team"] == opponent].iloc[0]     if both_adv is not None and not both_adv[both_adv["team"] == opponent].empty     else None

        sp_gap  = (float(prim_sp["rating"]) - float(opp_sp["rating"]))   if prim_sp  is not None and opp_sp  is not None else None
        ppa_gap = (float(prim_adv["off_ppa"]) - float(opp_adv["off_ppa"])) if prim_adv is not None and opp_adv is not None else None

        # ── Similar opponent lookup ─────────────────────────────────────────
        # Find teams that look like the opponent (SP+ rating ±5, similar off/def PPA)
        # then check how primary_team performed against those teams historically
        similar_opponents_data = None
        if opp_sp is not None and opp_adv is not None:
            opp_rating   = float(opp_sp["rating"])
            opp_off_ppa  = float(opp_adv["off_ppa"])
            opp_def_ppa  = float(opp_adv["def_ppa"])

            similar_opponents_data = safe_query(f"""
                WITH opp_similar AS (
                    -- Teams with similar SP+ and PPA profile to {opponent}
                    SELECT
                        sp.team,
                        sp.season,
                        sp.rating,
                        adv.off_ppa,
                        adv.def_ppa,
                        adv.def_havoc_total,
                        abs(sp.rating   - {opp_rating:.1f})  AS sp_diff,
                        abs(adv.off_ppa - {opp_off_ppa:.4f}) AS off_diff,
                        abs(adv.def_ppa - {opp_def_ppa:.4f}) AS def_diff
                    FROM cfbd.sp_ratings sp
                    JOIN cfbd.advanced_stats adv
                      ON sp.team = adv.team AND sp.season = adv.season
                    WHERE sp.team != '{opponent}'
                      AND abs(sp.rating - {opp_rating:.1f}) < 8
                    ORDER BY sp_diff + off_diff * 10 + def_diff * 10
                    LIMIT 15
                ),
                primary_vs_similar AS (
                    -- Games where primary_team faced one of those similar teams
                    SELECT
                        g.season,
                        g.week,
                        CASE WHEN g.home_team = '{primary_team}' THEN g.away_team ELSE g.home_team END AS sim_opponent,
                        g.home_points,
                        g.away_points,
                        l.spread,
                        l.spread_covered,
                        l.ou_result,
                        l.actual_margin,
                        os.rating      AS opp_sp_rating,
                        os.off_ppa,
                        os.def_ppa,
                        os.sp_diff,
                        CASE WHEN g.home_team = '{primary_team}'
                             THEN g.home_points - g.away_points
                             ELSE g.away_points - g.home_points
                        END AS primary_margin
                    FROM cfbd.games g
                    JOIN cfbd.lines l ON g.game_id = l.game_id
                    JOIN opp_similar os
                      ON os.team = CASE WHEN g.home_team = '{primary_team}' THEN g.away_team ELSE g.home_team END
                      AND os.season = g.season
                    WHERE (g.home_team = '{primary_team}' OR g.away_team = '{primary_team}')
                      AND l.spread IS NOT NULL
                      AND l.spread_covered IS NOT NULL
                    ORDER BY os.sp_diff ASC, g.season DESC
                )
                SELECT * FROM primary_vs_similar
                LIMIT 20
            """)

        # ── Four column layout ──────────────────────────────────────────────
        col_eff, col_sim, col_spread_ctx, col_verdict = st.columns([2, 2, 2, 2], gap="medium")

        with col_eff:
            st.markdown("**Efficiency head-to-head**")

            def stat_row(label, prim_val, opp_val, higher_is_better=True):
                if prim_val is None or opp_val is None:
                    return
                pv, ov = float(prim_val), float(opp_val)
                prim_wins = pv > ov if higher_is_better else pv < ov
                prim_color = "#39ff6e" if prim_wins else "#e74c3c"
                opp_color  = "#39ff6e" if not prim_wins else "#e74c3c"
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:0.78rem;padding:0.2rem 0;"
                    f"border-bottom:1px solid rgba(77,184,212,0.1)'>"
                    f"<span style='color:{prim_color}'>{pv:.2f}</span>"
                    f"<span style='color:#a09880;font-size:0.68rem'>{label}</span>"
                    f"<span style='color:{opp_color}'>{ov:.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"font-size:0.65rem;color:#a09880;letter-spacing:2px;"
                f"margin-bottom:0.4rem'>"
                f"<span>{primary_team[:12]}</span><span></span>"
                f"<span>{opponent[:12]}</span></div>",
                unsafe_allow_html=True,
            )

            if prim_sp is not None and opp_sp is not None:
                stat_row("SP+ Overall", prim_sp["rating"], opp_sp["rating"])
                stat_row("SP+ Offense", prim_sp["offense"], opp_sp["offense"])
                stat_row("SP+ Defense", prim_sp["defense"], opp_sp["defense"], higher_is_better=False)

            if prim_adv is not None and opp_adv is not None:
                stat_row("Off PPA",         prim_adv["off_ppa"],          opp_adv["off_ppa"])
                stat_row("Def PPA",         prim_adv["def_ppa"],          opp_adv["def_ppa"],          higher_is_better=False)
                stat_row("Off Success %",   prim_adv["off_success_rate"], opp_adv["off_success_rate"])
                stat_row("Def Success %",   prim_adv["def_success_rate"], opp_adv["def_success_rate"], higher_is_better=False)
                stat_row("Def Havoc",       prim_adv["def_havoc_total"],  opp_adv["def_havoc_total"])
                stat_row("Rush Off PPA",    prim_adv["off_rush_ppa"],     opp_adv["off_rush_ppa"])

            if sp_gap is not None:
                gap_color = "#39ff6e" if sp_gap > 0 else "#e74c3c"
                st.markdown(
                    f"<div style='margin-top:0.6rem;text-align:center;"
                    f"font-size:0.75rem;color:#a09880'>SP+ Gap: "
                    f"<b style='color:{gap_color}'>{sp_gap:+.1f}</b></div>",
                    unsafe_allow_html=True,
                )

        with col_sim:
            st.markdown(f"**{primary_team} vs {opponent}-like teams**")
            st.caption(f"Historical results vs opponents with similar SP+/PPA profile to {opponent}")

            if similar_opponents_data is not None and not similar_opponents_data.empty:
                sdf = similar_opponents_data

                # Summary stats
                cover_rate = sdf["spread_covered"].mean() * 100 if "spread_covered" in sdf else None
                avg_margin = sdf["primary_margin"].mean()        if "primary_margin" in sdf else None
                over_rate  = (sdf["ou_result"] == "over").mean() * 100 if "ou_result" in sdf else None
                n_games    = len(sdf)

                c1, c2 = st.columns(2)
                if cover_rate is not None:
                    cover_color = "#39ff6e" if cover_rate > 52 else "#e74c3c"
                    c1.metric("Cover rate vs similar", f"{cover_rate:.1f}%", border=True)
                if avg_margin is not None:
                    c2.metric("Avg margin vs similar", f"{avg_margin:+.1f} pts", border=True)

                st.caption(f"Based on {n_games} games vs {opponent}-like opponents")

                # Game log
                for _, row in sdf.head(8).iterrows():
                    covered = row.get("spread_covered")
                    result_icon = "✅" if covered else "❌"
                    margin = row.get("primary_margin", 0)
                    st.markdown(
                        f"<div style='font-size:0.72rem;padding:0.15rem 0.5rem;"
                        f"border-left:2px solid rgba(77,184,212,0.2);"
                        f"margin:0.1rem 0;line-height:1.4'>"
                        f"{result_icon} <b>{row['sim_opponent']}</b> "
                        f"<span style='color:#a09880'>({row['season']} Wk{int(row['week'])})</span> "
                        f"<span style='color:#ffcc44'>{margin:+.0f} pts</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                # Key takeaway
                if cover_rate is not None:
                    if cover_rate > 60:
                        st.success(f"✅ {primary_team} covers {cover_rate:.0f}% vs {opponent}-type teams", icon=":material/trending_up:")
                    elif cover_rate < 40:
                        st.error(f"❌ {primary_team} covers only {cover_rate:.0f}% vs {opponent}-type teams", icon=":material/trending_down:")
                    else:
                        st.caption(f"→ {cover_rate:.0f}% cover rate — no strong lean vs this profile")
            else:
                st.caption(f"Not enough historical data vs {opponent}-like opponents.")

        with col_spread_ctx:
            st.markdown("**Spread context**")

            spread_display = "Pick 'em" if is_pk else (
                f"{primary_team} {'−' if primary_is_fav else '+'}"
                f"{'%.0f' % abs_spread}"
            )
            st.markdown(
                f"<div style='background:#0a2a36;border:1px solid rgba(200,80,26,0.4);"
                f"padding:0.8rem 1rem;font-size:0.9rem;text-align:center;"
                f"margin-bottom:0.6rem'>"
                f"<div style='color:#a09880;font-size:0.65rem;letter-spacing:3px'>LINE</div>"
                f"<div style='font-size:1.3rem;color:#ffcc44;font-weight:bold'>"
                f"{spread_display}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Historical ROI for this situation
            if primary_is_fav:
                sit_roi  = float(p.get("home_fav_roi",  0) or 0)
                sit_name = "home favorite"
                sit_bets = int(p.get("home_fav_bets", 0) or 0)
            elif primary_is_dog:
                sit_roi  = float(p.get("home_dog_roi",  0) or 0)
                sit_name = "home underdog"
                sit_bets = int(p.get("home_dog_bets", 0) or 0)
            else:
                sit_roi  = float(p.get("home_roi", 0) or 0)
                sit_name = "home (all)"
                sit_bets = int(p.get("home_bets", 0) or 0)

            roi_color = "#39ff6e" if sit_roi > 0 else "#e74c3c"
            st.markdown(
                f"<div style='font-size:0.8rem;color:#a09880'>ROI as "
                f"<b style='color:#e8dcc8'>{sit_name}</b></div>"
                f"<div style='font-size:1.5rem;color:{roi_color};font-weight:bold'>"
                f"{sit_roi:+.1f}%</div>"
                f"<div style='font-size:0.72rem;color:#a09880'>{sit_bets} games</div>",
                unsafe_allow_html=True,
            )

            # Opponent historical ROI in this role
            if opp_profile is not None and not opp_profile.empty:
                op = opp_profile.iloc[0]
                if primary_is_fav:   # opponent is away dog
                    opp_sit_roi  = float(op.get("away_dog_roi", 0) or 0)
                    opp_sit_name = "away underdog"
                    opp_sit_bets = int(op.get("away_dog_bets", 0) or 0)
                elif primary_is_dog: # opponent is away fav
                    opp_sit_roi  = float(op.get("away_fav_roi", 0) or 0)
                    opp_sit_name = "away favorite"
                    opp_sit_bets = int(op.get("away_fav_bets", 0) or 0)
                else:
                    opp_sit_roi  = float(op.get("away_roi", 0) or 0)
                    opp_sit_name = "away (all)"
                    opp_sit_bets = int(op.get("away_bets", 0) or 0)

                st.space("small")
                opp_roi_color = "#39ff6e" if opp_sit_roi > 0 else "#e74c3c"
                st.markdown(
                    f"<div style='font-size:0.8rem;color:#a09880'>{opponent} ROI as "
                    f"<b style='color:#e8dcc8'>{opp_sit_name}</b></div>"
                    f"<div style='font-size:1.3rem;color:{opp_roi_color};font-weight:bold'>"
                    f"{opp_sit_roi:+.1f}%</div>"
                    f"<div style='font-size:0.72rem;color:#a09880'>{opp_sit_bets} games</div>",
                    unsafe_allow_html=True,
                )

        with col_verdict:
            st.markdown("**Signal stack → Verdict**")

            signals = []
            flags   = []

            # PPA gap
            if ppa_gap is not None:
                if ppa_gap > 0.30:
                    signals.append(("✅", f"PPA gap {ppa_gap:+.3f} — STRONG (>0.30)"))
                elif ppa_gap > 0.15:
                    signals.append(("✅", f"PPA gap {ppa_gap:+.3f} — edge (>0.15)"))
                elif ppa_gap > 0.05:
                    signals.append(("🟡", f"PPA gap {ppa_gap:+.3f} — marginal"))
                elif ppa_gap < -0.15:
                    flags.append(("🚨", f"PPA gap {ppa_gap:+.3f} — opponent efficiency edge"))
                else:
                    signals.append(("⬜", f"PPA gap {ppa_gap:+.3f} — no edge"))

            # SP+ gap
            if sp_gap is not None:
                if sp_gap > 10:
                    signals.append(("✅", f"SP+ gap {sp_gap:+.1f} — clear advantage"))
                elif sp_gap < -10:
                    flags.append(("🚨", f"SP+ gap {sp_gap:+.1f} — clear disadvantage"))
                else:
                    signals.append(("🟡", f"SP+ gap {sp_gap:+.1f} — close matchup"))

            # Team tier
            if tier in ("STRONG_FADE", "FADE") and primary_is_fav:
                flags.append(("🚨", f"{primary_team} is {tier} — avoid as favorite"))
            elif tier in ("ELITE", "STRONG") and primary_is_dog:
                signals.append(("✅", f"{primary_team} {tier} tier underdog"))
            elif tier in ("ELITE", "STRONG") and primary_is_fav:
                signals.append(("✅", f"{primary_team} {tier} tier — consistent ATS"))

            if opp_profile is not None and not opp_profile.empty:
                opp_tier = str(opp_profile.iloc[0].get("tier", "NEUTRAL"))
                if opp_tier in ("STRONG_FADE", "FADE"):
                    signals.append(("✅", f"Opponent {opp_tier} — fade candidate"))
                elif opp_tier in ("ELITE", "STRONG") and primary_is_fav:
                    flags.append(("⚠️", f"Opponent {opp_tier} — tough cover"))

            # Similar opponent history
            if similar_opponents_data is not None and not similar_opponents_data.empty:
                sdf = similar_opponents_data
                cover_rate = sdf["spread_covered"].mean() * 100
                if cover_rate > 60:
                    signals.append(("✅", f"Covers {cover_rate:.0f}% vs {opponent}-type teams"))
                elif cover_rate < 40:
                    flags.append(("🚨", f"Only {cover_rate:.0f}% cover vs {opponent}-type teams"))
                else:
                    signals.append(("🟡", f"{cover_rate:.0f}% cover vs {opponent}-type teams"))

            # Spread range
            if not is_pk:
                if 3 <= abs_spread <= 14:
                    signals.append(("✅", f"Spread {spread_val} in optimal range (3-14)"))
                elif abs_spread > 17:
                    signals.append(("⚠️", f"Spread {spread_val} — large spread caution"))

            # Sit ROI
            if sit_roi > 20:
                signals.append(("✅", f"ROI as {sit_name}: {sit_roi:+.1f}%"))
            elif sit_roi < -20:
                flags.append(("🚨", f"ROI as {sit_name}: {sit_roi:+.1f}% — avoid"))

            # Render flags first
            for icon, msg in flags:
                st.markdown(
                    f"<div style='background:rgba(231,76,60,0.15);border-left:3px solid #e74c3c;"
                    f"padding:0.3rem 0.6rem;margin:0.2rem 0;font-size:0.78rem'>"
                    f"{icon} {msg}</div>",
                    unsafe_allow_html=True,
                )
            for icon, msg in signals:
                bg     = "rgba(57,255,110,0.08)"  if icon == "✅" else                          "rgba(255,204,68,0.08)"   if icon == "🟡" else                          "rgba(160,152,128,0.06)"
                border = "#39ff6e" if icon == "✅" else                          "#ffcc44" if icon == "🟡" else "#a09880"
                st.markdown(
                    f"<div style='background:{bg};border-left:3px solid {border};"
                    f"padding:0.3rem 0.6rem;margin:0.2rem 0;font-size:0.78rem'>"
                    f"{icon} {msg}</div>",
                    unsafe_allow_html=True,
                )

            # Verdict
            green_count = sum(1 for i, _ in signals if i == "✅")
            red_count   = len([f for f in flags if f[0] == "🚨"])

            if red_count >= 2:
                verdict_color, verdict_text, verdict_icon = "#e74c3c", "PASS — Multiple red flags", "🚫"
            elif red_count == 1 and green_count < 2:
                verdict_color, verdict_text, verdict_icon = "#e67e22", "LEAN PASS — Red flag present", "⚠️"
            elif green_count >= 4:
                verdict_color, verdict_text, verdict_icon = "#39ff6e", "STRONG BET", "💰"
            elif green_count >= 2:
                verdict_color, verdict_text, verdict_icon = "#ffcc44", "LEAN BET", "📊"
            else:
                verdict_color, verdict_text, verdict_icon = "#a09880", "PASS — Insufficient edge", "⏭️"

            st.markdown(
                f"<div style='background:{verdict_color}22;border:2px solid {verdict_color};"
                f"padding:0.8rem 1rem;text-align:center;margin-top:0.5rem'>"
                f"<div style='font-size:1.5rem'>{verdict_icon}</div>"
                f"<div style='color:{verdict_color};font-size:1rem;font-weight:bold;"
                f"letter-spacing:2px'>{verdict_text}</div>"
                f"<div style='color:#a09880;font-size:0.72rem;margin-top:0.3rem'>"
                f"{green_count} green · {red_count} red flags</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — LINE ACCURACY (original dashboard)
# ═════════════════════════════════════════════════════════════════════════════

with tab_accuracy:

    col_s, col_p, _ = st.columns([1, 1, 3])
    with col_s:
        selected_season = st.selectbox(
            "Season", ["All"] + [str(s) for s in available_seasons], key="acc_season"
        )
    with col_p:
        providers_df = safe_query(
            "SELECT DISTINCT provider FROM cfbd.lines WHERE provider IS NOT NULL ORDER BY provider"
        )
        providers = providers_df["provider"].tolist() if providers_df is not None else []
        selected_provider = st.selectbox(
            "Provider", ["consensus (avg)"] + providers, key="acc_provider"
        )

    season_filter   = f"AND season = {selected_season}" if selected_season != "All" else ""
    provider_filter = f"AND provider = '{selected_provider}'" if selected_provider != "consensus (avg)" else ""

    # Top-line metrics
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
                  delta=f"{r['ats_pct'] - 50:.1f}% vs 50%", border=True)
        c3.metric("Over Rate", f"{r['over_pct']}%",
                  delta=f"{r['over_pct'] - 50:.1f}% vs 50%", border=True)
        c4.metric("Avg Spread Error", f"{r['avg_margin_error']} pts", border=True)
        c5.metric("Avg O/U Error", f"{r['avg_ou_error']} pts", border=True)

    # Conference ATS
    st.subheader("ATS Cover Rate by Conference")
    conf_data = safe_query(f"""
        SELECT
            home_conference as conference,
            count(*) as games,
            round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
            round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE spread_result in ('covered','missed') AND home_conference IS NOT NULL
        {season_filter} {provider_filter}
        GROUP BY home_conference HAVING count(*) >= 30
        ORDER BY ats_pct DESC
    """)

    if conf_data is not None and not conf_data.empty:
        fig = go.Figure(go.Bar(
            x=conf_data["conference"],
            y=conf_data["ats_pct"],
            marker_color=["#2ecc71" if v > 50 else "#e74c3c" for v in conf_data["ats_pct"]],
            hovertemplate="%{x}<br>ATS: %{y:.1f}%<extra></extra>",
        ))
        fig.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
        fig.update_layout(
            yaxis_range=[40, 60], xaxis_title=None, yaxis_title="ATS Cover %",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"), margin=dict(l=0, r=0, t=10, b=0), height=280,
        )
        st.plotly_chart(fig)

    # Spread size accuracy
    st.subheader("Accuracy vs Spread Size")
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
            round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE spread_result in ('covered','missed')
        {season_filter} {provider_filter}
        GROUP BY 1 ORDER BY min(spread_abs)
    """)

    with col1:
        st.markdown("**ATS Cover % by Spread Size**")
        if spread_size is not None and not spread_size.empty:
            fig2 = go.Figure(go.Bar(
                x=spread_size["spread_bucket"], y=spread_size["ats_pct"],
                marker_color=["#2ecc71" if v > 50 else "#e74c3c" for v in spread_size["ats_pct"]],
            ))
            fig2.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
            fig2.update_layout(
                yaxis_range=[40, 65], plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#FAFAFA"),
                margin=dict(l=0, r=0, t=10, b=0), height=260,
            )
            st.plotly_chart(fig2)

    with col2:
        st.markdown("**Over % by Spread Size**")
        if spread_size is not None and not spread_size.empty:
            fig3 = go.Figure(go.Bar(
                x=spread_size["spread_bucket"], y=spread_size["over_pct"],
                marker_color=["#3498db" if v > 50 else "#e67e22" for v in spread_size["over_pct"]],
            ))
            fig3.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.5)
            fig3.update_layout(
                yaxis_range=[40, 65], plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#FAFAFA"),
                margin=dict(l=0, r=0, t=10, b=0), height=260,
            )
            st.plotly_chart(fig3)

    # Recent games
    st.subheader("Recent Games")
    recent = safe_query(f"""
        SELECT
            season, week, home_team, away_team,
            home_score, away_score, spread, over_under,
            spread_result, ou_bucket,
            round(margin_vs_spread, 1) as margin_vs_spread,
            round(total_vs_ou, 1) as total_vs_ou,
            home_sp_rating, away_sp_rating
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE spread_result != 'unknown'
        {season_filter} {provider_filter}
        ORDER BY season DESC, week DESC
        LIMIT 50
    """)

    if recent is not None and not recent.empty:
        st.dataframe(
            recent, hide_index=True,
            column_config={
                "spread_result": st.column_config.TextColumn("ATS Result"),
                "ou_bucket":     st.column_config.TextColumn("O/U Result"),
            },
        )
