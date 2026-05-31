"""
Reading page — Hardcover fiction + nonfiction tracking.
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

st.set_page_config(page_title="Reading · Operating Narcisystem", page_icon="📚", layout="wide")
st.title("📚 Reading")
st.caption("Hardcover · 2026")


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
# Summary metrics
# ---------------------------------------------------------------------------

summary = safe_query("SELECT * FROM hardcover.reading_summary WHERE year = 2026")

if summary is not None and not summary.empty:
    r = summary.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Read", int(r["total_read"]))
    c2.metric(
        "Fiction",
        int(r["fiction_read"]),
        f"goal: {int(r['fiction_goal'])}",
    )
    c3.metric(
        "Nonfiction",
        int(r["nonfiction_read"]),
        f"goal: {int(r['nonfiction_goal'])}",
    )
    c4.metric("Unclassified", int(r["unknown_classification"]))

    st.markdown("**Progress**")
    fc1, fc2 = st.columns(2)
    with fc1:
        fp = float(r["fiction_progress_pct"])
        st.progress(min(int(fp), 100), text=f"Fiction — {fp:.1f}%")
    with fc2:
        np_ = float(r["nonfiction_progress_pct"])
        st.progress(min(int(np_), 100), text=f"Nonfiction — {np_:.1f}%")
else:
    st.info("No reading data. Run `python run_pipelines.py --only hardcover`.")

# ---------------------------------------------------------------------------
# Book list
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Books Read · 2026")

col1, col2 = st.columns([1, 3])
with col1:
    filter_type = st.selectbox("Filter", ["All", "Fiction", "Nonfiction", "Unknown"])

type_map = {
    "Fiction": "fiction",
    "Nonfiction": "nonfiction",
    "Unknown": "unknown",
}

if filter_type == "All":
    where = "WHERE year = 2026"
else:
    where = f"WHERE year = 2026 AND classification = '{type_map[filter_type]}'"

books = safe_query(f"""
    SELECT
        marked_read_at::date as read_date,
        title,
        authors,
        classification,
        cached_tags
    FROM hardcover.books_read
    {where}
    ORDER BY marked_read_at DESC
""")

if books is not None and not books.empty:
    st.dataframe(
        books,
        width="stretch",
        hide_index=True,
        column_config={
            "classification": st.column_config.TextColumn("Type"),
            "cached_tags": st.column_config.TextColumn("Tags"),
        },
    )
else:
    st.info("No books found for that filter.")
