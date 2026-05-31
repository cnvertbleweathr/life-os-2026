"""
Goals page — full goal inventory and progress tracking.
"""

import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme
apply_theme()

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

st.set_page_config(page_title="Goals · Operating Narcisystem", page_icon="🎯", layout="wide")
st.title("🎯 Goals · 2026")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


goal_progress = safe_query("""
    SELECT domain, goal_key, target_numeric, current_value, progress_percent, status
    FROM main_marts.mart_goal_progress
    ORDER BY domain, goal_key
""")

if goal_progress is None or goal_progress.empty:
    st.info("No goal data. Run `dbt run` after syncing pipelines.")
    st.stop()

domains = sorted(goal_progress["domain"].unique().tolist())
selected_domain = st.selectbox("Domain", ["All"] + [d.title() for d in domains])

if selected_domain != "All":
    filtered = goal_progress[goal_progress["domain"].str.lower() == selected_domain.lower()]
else:
    filtered = goal_progress

for domain in (
    [selected_domain.lower()] if selected_domain != "All" else domains
):
    subset = filtered[filtered["domain"] == domain]
    if subset.empty:
        continue

    st.subheader(domain.title())

    for _, row in subset.iterrows():
        label = row["goal_key"].replace("_", " ").title()
        pct = row.get("progress_percent")
        current = row.get("current_value")
        target = row.get("target_numeric")
        status = row.get("status", "")

        col_label, col_bar = st.columns([1, 3])
        with col_label:
            if current is not None and not pd.isna(current) and target is not None and not pd.isna(target):
                st.markdown(f"**{label}**  \n`{current:.0f}` / `{target:.0f}`")
            else:
                st.markdown(f"**{label}**  \n`{status}`")

        with col_bar:
            if pct is not None and not pd.isna(pct):
                st.progress(min(int(pct), 100), text=f"{pct:.1f}%")
            else:
                st.markdown(f"_{status}_")

    st.divider()

# Raw table toggle
with st.expander("Raw data"):
    st.dataframe(filtered, use_container_width=True, hide_index=True)
