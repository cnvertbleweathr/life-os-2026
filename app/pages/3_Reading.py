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
    c1.metric("Total Read", int(r["total_read"]), border=True)
    c2.metric(
        "Fiction",
        int(r["fiction_read"]),
        f"goal: {int(r['fiction_goal'])}",
        border=True,
    )
    c3.metric(
        "Nonfiction",
        int(r["nonfiction_read"]),
        f"goal: {int(r['nonfiction_goal'])}",
        border=True,
    )
    c4.metric("Unclassified", int(r["unknown_classification"]), border=True)

    st.markdown("**Progress**")
    fc1, fc2 = st.columns(2)
    with fc1:
        fp = float(r["fiction_progress_pct"])
        st.progress(min(int(fp), 100), text=f"Fiction — {fp:.1f}%")
    with fc2:
        np_ = float(r["nonfiction_progress_pct"])
        st.progress(min(int(np_), 100), text=f"Nonfiction — {np_:.1f}%")
else:
    st.caption("No reading data. Run `python run_pipelines.py --only hardcover`.")

# ---------------------------------------------------------------------------
# Books in Progress
# ---------------------------------------------------------------------------

in_progress = safe_query("""
    SELECT
        title,
        authors,
        classification,
        cached_tags
    FROM hardcover.books_read
    WHERE year = year(current_date)
      AND status = 'reading'
    ORDER BY marked_read_at DESC
""")

# Fallback — some Hardcover configs use different status values
if in_progress is None or in_progress.empty:
    in_progress = safe_query("""
        SELECT title, authors, classification, cached_tags
        FROM hardcover.books_read
        WHERE year = year(current_date)
          AND lower(status) IN ('reading', 'in progress', 'current', 'currently reading')
        ORDER BY marked_read_at DESC
    """)

if in_progress is not None and not in_progress.empty:
    st.subheader("📖 Currently Reading")
    cols = st.columns(min(len(in_progress), 3))
    for i, (_, book) in enumerate(in_progress.iterrows()):
        with cols[i % 3]:
            classification = str(book.get("classification", "")).lower()
            type_badge_color = "#0B5324" if classification == "fiction" else "#D97706"
            type_label = classification.title() if classification else "Unknown"
            st.markdown(
                f"<div style='background:#373D39;border:1px solid #434A45;"
                f"border-top:3px solid {type_badge_color};"
                f"border-radius:6px;padding:1rem 1.1rem'>"
                f"<div style='font-size:0.6rem;font-weight:600;letter-spacing:2px;"
                f"text-transform:uppercase;color:#A9B2AC;margin-bottom:0.4rem'>"
                f"{type_label}</div>"
                f"<div style='font-weight:600;font-size:0.9rem;color:#F5EFEB;"
                f"line-height:1.4;margin-bottom:0.3rem'>{book['title']}</div>"
                f"<div style='font-size:0.75rem;color:#A9B2AC'>{book['authors']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.space("small")
elif in_progress is not None:
    st.subheader("📖 Currently Reading")
    st.caption("No books currently marked as 'reading' in Hardcover.")

st.divider()

# ---------------------------------------------------------------------------
# Book list
# ---------------------------------------------------------------------------

st.subheader("Books read · 2026")

col1, col2 = st.columns([1, 3])
with col1:
    filter_type = st.segmented_control("Filter", ["All", "Fiction", "Nonfiction", "Unknown"], default="All")

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
    st.caption("No books found for that filter.")
