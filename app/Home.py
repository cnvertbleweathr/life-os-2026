"""
Life OS — Main Streamlit app.

Multi-page app. This file is the home page / system overview.
Pages live in app/pages/.

Run with:
  streamlit run app/Home.py
"""

import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")

st.set_page_config(
    page_title="Life OS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧭 Life OS")
st.caption("Personal operating system · 2026")

# ---------------------------------------------------------------------------
# DB connection helper
# ---------------------------------------------------------------------------

@st.cache_resource
def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query failed: {e}")
        return None


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------

st.subheader("System Status")

healthcheck = safe_query("SELECT * FROM main_marts.mart_lifeos_healthcheck")
if healthcheck is not None and not healthcheck.empty:
    st.dataframe(healthcheck, use_container_width=True)
else:
    st.info("Run `dbt run` to populate the healthcheck mart.")

# ---------------------------------------------------------------------------
# Goals overview — quick scoreboard
# ---------------------------------------------------------------------------

st.subheader("Goals · 2026")

goal_progress = safe_query("""
    SELECT domain, goal_key, target_numeric, current_value, progress_percent, status
    FROM main_marts.mart_goal_progress
    ORDER BY domain, goal_key
""")

if goal_progress is not None and not goal_progress.empty:
    domains = goal_progress["domain"].unique().tolist()
    cols = st.columns(len(domains))
    for col, domain in zip(cols, domains):
        with col:
            st.markdown(f"**{domain.title()}**")
            subset = goal_progress[goal_progress["domain"] == domain]
            for _, row in subset.iterrows():
                pct = row.get("progress_percent")
                label = row["goal_key"].replace("_", " ").title()
                if pct is not None and not pd.isna(pct):
                    st.progress(min(int(pct), 100), text=f"{label} · {pct:.0f}%")
                else:
                    status = row.get("status", "—")
                    st.markdown(f"- {label}: `{status}`")
else:
    st.info("No goal progress data. Run pipelines + `dbt run`.")

# ---------------------------------------------------------------------------
# Sidebar nav hint
# ---------------------------------------------------------------------------

st.sidebar.success("Navigate using the pages above.")
