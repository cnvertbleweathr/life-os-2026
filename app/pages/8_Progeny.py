"""
Progeny — the kids' development: timeline, learning paths, CDC milestones,
reading, baby prep.

Reads dbt marts only (main_marts.mart_progeny_*). The quick-entry forms append to
data/progeny/*.jsonl through progeny/store.py and never touch DuckDB; the daily
sync loads them (pipelines/progeny_pipeline.py → dbt), so new entries show up
after the next sync. Kids and reference options come from config files:
data/progeny/kids.yaml (gitignored) and progeny/reference/*.yaml.
"""

from __future__ import annotations

import html
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from ons_theme import apply_theme, section_header  # noqa: E402
from progeny import store  # noqa: E402

st.set_page_config(page_title="Progeny · ONS", page_icon="🌱", layout="wide")
apply_theme()

DB_PATH = os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))
SYNC_HINT = ("New entries show up after the next daily sync, or run "
             "`python scripts/daily_sync.py --only progeny dbt`.")
PREP_CATEGORIES = ["Gear", "Nursery", "Hospital", "Feeding", "Health", "Admin", "Family", "Other"]
EVENT_ICONS = {"quote": "💬", "first": "⭐", "milestone": "🧭", "path": "🪜"}

st.markdown("""
<style>
  .pg-card { background: var(--bg-surface); border: 1px solid var(--border);
             border-left: 3px solid var(--brand-primary); border-radius: 6px;
             padding: 0.9rem 1.1rem; margin-bottom: 0.6rem; }
  .pg-card.amber { border-left-color: var(--accent-orange); }
  .pg-kicker { font-size: 0.62rem; font-weight: 600; letter-spacing: 2px;
               text-transform: uppercase; color: var(--text-muted); }
  .pg-title { font-size: 1.05rem; font-weight: 600; margin: 0.15rem 0 0.35rem; }
  .pg-body { font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; }
  .pg-body ul { margin: 0.3rem 0 0 1.1rem; padding: 0; }
  .pg-quote { font-style: italic; }
  .pg-event { display: flex; gap: 0.8rem; padding: 0.55rem 0;
              border-bottom: 1px solid var(--border); }
  .pg-event-icon { font-size: 1.1rem; width: 1.6rem; text-align: center; }
  .pg-event-meta { font-size: 0.68rem; letter-spacing: 0.5px; color: var(--text-muted);
                   text-transform: uppercase; }
  .pg-ms { font-size: 0.85rem; padding: 0.2rem 0; }
  .pg-ms.done { color: var(--text-muted); }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def mart(name: str) -> pd.DataFrame:
    """A progeny mart, or an empty frame if the warehouse/mart isn't there yet."""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        try:
            return con.execute(f"SELECT * FROM main_marts.{name}").df()
        finally:
            con.close()
    except Exception:
        return pd.DataFrame()


def esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return ""
    return html.escape(str(value))


def fmt_date(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%b %-d, %Y")


def save(kind: str, fields: dict, label: str, entry_id: str | None = None) -> bool:
    try:
        store.append_entry(kind, fields, entry_id=entry_id)
    except ValueError as e:
        st.toast(f"Not saved: {e}", icon="⚠️")
        return False
    st.toast(f"Saved {label}. It appears after the next sync.", icon="✅")
    return True


def _plain(v):
    """DataFrame cell → JSON-friendly value (NaT/NaN → None, Timestamp → date)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.date() if isinstance(v, pd.Timestamp) else v


# Button callbacks run before the page redraws, so the toast shows and the row
# flips to "logged" in the same run. Session sets remember clicks until the sync
# catches up.
def mark_seen(kid_id: str, milestone_id: str) -> None:
    if save("milestones", {"kid": kid_id, "milestone_id": milestone_id,
                           "observed_date": date.today()}, "milestone"):
        st.session_state.setdefault("pg_ms_logged", set()).add((kid_id, milestone_id))


def mark_done(task: dict) -> None:
    fields = {k: _plain(task.get(k)) for k in ("task", "category", "due_date", "created_date")}
    if save("prep_tasks", {**fields, "done_date": date.today()}, "task", entry_id=task["task_id"]):
        st.session_state.setdefault("pg_prep_done", set()).add(task["task_id"])


try:
    KIDS = store.load_kids()
    kids_error = None
except Exception as e:  # malformed kids.yaml
    KIDS, kids_error = [], str(e)

KID_NAMES = {k["kid_id"]: k["display_name"] for k in KIDS}
BORN_IDS = [k["kid_id"] for k in KIDS if k["birthdate"]]
today = date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Header + countdowns
# ─────────────────────────────────────────────────────────────────────────────

st.title("🌱 Progeny")
st.caption("Quotes, firsts, milestones and learning, logged as they happen.")

if kids_error:
    st.error(f"Couldn't read `data/progeny/kids.yaml`: {kids_error}")
    st.stop()

if not KIDS:
    st.info(
        "**Set up Progeny.** Create your kids config (it's gitignored and never committed):\n\n"
        "```bash\nmkdir -p data/progeny\n"
        "cp progeny/config/kids.example.yaml data/progeny/kids.yaml\n```\n\n"
        "Edit names and dates, then reload this page.",
        icon="🌱",
    )
    st.stop()

kids_df = mart("mart_progeny_kids")
if kids_df.empty:
    st.info(f"Kids are configured but not loaded into the warehouse yet. {SYNC_HINT}", icon="⏳")
else:
    cols = st.columns(max(len(kids_df), 1))
    for col, (_, k) in zip(cols, kids_df.iterrows()):
        with col:
            if k["is_born"]:
                days = int(k["days_to_birthday"])
                st.metric(
                    label=f"{k['display_name']} · {k['age_label']}",
                    value="🎂 Today!" if days == 0 else f"{days} days",
                    delta=f"until turning {int(k['turning_age'])} · {fmt_date(k['next_birthday'])}",
                    delta_color="off", delta_arrow="off",
                    border=True,
                )
            else:
                days = int(k["days_to_due"])
                st.metric(
                    label=f"{k['display_name']} · due {fmt_date(k['due_date'])}",
                    value=f"{days} days" if days >= 0 else f"{-days} days past due",
                    delta="until due date" if days >= 0 else "add the birthdate to kids.yaml",
                    delta_color="off", delta_arrow="off",
                    border=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# This week's focus (one learning path per kid, rotating weekly)
# ─────────────────────────────────────────────────────────────────────────────

paths_df = mart("mart_progeny_paths")
if not paths_df.empty:
    section_header("This week's focus")
    week = today.isocalendar().week
    kid_ids = [k for k in paths_df["kid_id"].unique()]
    fcols = st.columns(len(kid_ids))
    for col, kid_id in zip(fcols, kid_ids):
        kp = paths_df[paths_df["kid_id"] == kid_id].sort_values("path_order").reset_index(drop=True)
        # Same path all week; cycles through every path in turn
        row = kp.iloc[week % len(kp)]
        acts = [a for a in str(row["focus_activities"] or "").split("\n") if a.strip()]
        status = ("Path complete. Keep practising" if row["is_complete"]
                  else f"Level {int(row['focus_level'])} of {int(row['total_levels'])}")
        with col:
            st.markdown(
                f"<div class='pg-card amber'>"
                f"<div class='pg-kicker'>{esc(row['display_name'])} · {esc(row['path_name'])} · {status}</div>"
                f"<div class='pg-title'>{esc(row['focus_level_name'])}</div>"
                f"<div class='pg-body'>{esc(row['focus_description'])}"
                f"<ul>{''.join(f'<li>{esc(a)}</li>' for a in acts)}</ul></div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Quick log
# ─────────────────────────────────────────────────────────────────────────────

milestone_ref = store.milestone_rows()
level_ref = store.path_level_rows()
titles_df = mart("mart_progeny_reading_titles")

with st.expander("➕ Quick log", expanded=False):
    kind = st.segmented_control(
        "Log a…",
        ["Quote", "First", "Book", "Learning", "Milestone", "Prep task"],
        default="Quote",
        key="pg_kind",
    )
    kid_opts = list(KID_NAMES)

    if kind == "Quote":
        with st.form("pg_quote", clear_on_submit=True):
            c1, c2 = st.columns([1, 1])
            kid = c1.selectbox("Kid", kid_opts, format_func=KID_NAMES.get)
            d = c2.date_input("Date", value=today, max_value=today)
            quote = st.text_area("What they said", height=80)
            context = st.text_input("Context (optional)", placeholder="at breakfast, in the car…")
            if st.form_submit_button("Save quote", type="primary", width="stretch"):
                save("quotes", {"kid": kid, "date": d, "quote": quote, "context": context}, "quote")

    elif kind == "First":
        with st.form("pg_first", clear_on_submit=True):
            c1, c2 = st.columns(2)
            kid = c1.selectbox("Kid", kid_opts, format_func=KID_NAMES.get)
            d = c2.date_input("Date", value=today, max_value=today)
            title = st.text_input("First what?", placeholder="First time riding a bike without help")
            notes = st.text_area("Notes (optional)", height=70)
            if st.form_submit_button("Save first", type="primary", width="stretch"):
                save("firsts", {"kid": kid, "date": d, "title": title, "notes": notes}, "first")

    elif kind == "Book":
        known = (titles_df.sort_values("times_read", ascending=False)["title"].drop_duplicates().tolist()
                 if not titles_df.empty else [])
        with st.form("pg_book", clear_on_submit=True):
            c1, c2 = st.columns(2)
            kids_sel = c1.multiselect("Read to", kid_opts, default=kid_opts[:1], format_func=KID_NAMES.get)
            d = c2.date_input("Date", value=today, max_value=today)
            title = st.selectbox("Title", known, index=None, accept_new_options=True,
                                 placeholder="Pick a past book or type a new one")
            author = st.text_input("Author (optional)")
            if st.form_submit_button("Save book", type="primary", width="stretch"):
                if not kids_sel:
                    st.toast("Pick at least one kid.", icon="⚠️")
                else:
                    for kid in kids_sel:
                        key = " ".join(str(title or "").lower().split())
                        seen = (not titles_df.empty and
                                ((titles_df["kid_id"] == kid) & (titles_df["title_key"] == key)).any())
                        save("books", {"kid": kid, "date": d, "title": title, "author": author,
                                       "repeat": bool(seen)}, f"book for {KID_NAMES[kid]}")

    elif kind == "Learning":
        level_opts = [(r["path_key"], r["level_key"]) for r in level_ref]
        level_label = {(r["path_key"], r["level_key"]):
                       f"{r['path_name']} → {r['level_num']}. {r['level_name']}" for r in level_ref}
        with st.form("pg_path", clear_on_submit=True):
            c1, c2 = st.columns(2)
            kid = c1.selectbox("Kid", [k for k in kid_opts if k in BORN_IDS] or kid_opts,
                               format_func=KID_NAMES.get)
            d = c2.date_input("Date", value=today, max_value=today)
            lvl = st.selectbox("Showed this level", level_opts, format_func=level_label.get)
            notes = st.text_input("What you saw (optional)")
            if st.form_submit_button("Save evidence", type="primary", width="stretch"):
                save("path_evidence", {"kid": kid, "path": lvl[0], "level": lvl[1], "date": d,
                                       "notes": notes}, "learning evidence")

    elif kind == "Milestone":
        ms_label = {m["milestone_id"]: f"{m['band_label']} · {m['domain_label'].split(' (')[0]} · {m['milestone']}"
                    for m in milestone_ref}
        with st.form("pg_ms", clear_on_submit=True):
            c1, c2 = st.columns(2)
            kid = c1.selectbox("Kid", [k for k in kid_opts if k in BORN_IDS] or kid_opts,
                               format_func=KID_NAMES.get)
            d = c2.date_input("Observed on", value=today, max_value=today)
            ms = st.selectbox("Milestone", list(ms_label), format_func=ms_label.get, index=None,
                              placeholder="Type to search the CDC checklist")
            notes = st.text_input("Notes (optional)")
            if st.form_submit_button("Save milestone", type="primary", width="stretch"):
                save("milestones", {"kid": kid, "milestone_id": ms, "observed_date": d,
                                    "notes": notes}, "milestone")

    elif kind == "Prep task":
        with st.form("pg_prep", clear_on_submit=True):
            task = st.text_input("Task", placeholder="Install the car seat")
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Category", PREP_CATEGORIES, accept_new_options=True)
            due = c2.date_input("Due", value=None)
            if st.form_submit_button("Add task", type="primary", width="stretch"):
                save("prep_tasks", {"task": task, "category": cat, "due_date": due}, "prep task")

    st.caption(SYNC_HINT)


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_tl, tab_paths, tab_ms, tab_read, tab_prep = st.tabs(
    ["Timeline", "Learning Paths", "Milestones", "Reading", "Baby Prep"]
)

# ── Timeline ─────────────────────────────────────────────────────────────────
with tab_tl:
    tl = mart("mart_progeny_timeline")
    if tl.empty:
        st.caption(f"No quotes, firsts, milestones or learning evidence yet. "
                   f"Use **Quick log** above. {SYNC_HINT}")
    else:
        c1, c2 = st.columns([1, 2])
        who = c1.segmented_control("Kid", ["All"] + list(tl["display_name"].dropna().unique()),
                                   default="All", key="pg_tl_kid")
        types = c2.pills("Show", list(EVENT_ICONS), default=list(EVENT_ICONS), selection_mode="multi",
                         format_func=lambda t: f"{EVENT_ICONS[t]} {t}", key="pg_tl_types")
        view = tl[tl["event_type"].isin(types or [])]
        if who and who != "All":
            view = view[view["display_name"] == who]
        if view.empty:
            st.caption("Nothing matches those filters.")
        rows = []
        for _, e in view.head(200).iterrows():
            title = esc(e["title"])
            if e["event_type"] == "quote":
                title = f"<span class='pg-quote'>“{title}”</span>"
            detail = f"<div class='pg-body'>{esc(e['detail'])}</div>" if esc(e["detail"]) else ""
            rows.append(
                f"<div class='pg-event'><div class='pg-event-icon'>{EVENT_ICONS[e['event_type']]}</div>"
                f"<div><div class='pg-event-meta'>{fmt_date(e['event_date'])} · {esc(e['display_name'])}"
                f"{' · ' + esc(e['age_at_event']) if esc(e['age_at_event']) else ''}</div>"
                f"<div>{title}</div>{detail}</div></div>"
            )
        st.markdown("".join(rows), unsafe_allow_html=True)
        if len(view) > 200:
            st.caption(f"Showing the latest 200 of {len(view)}.")

# ── Learning paths ───────────────────────────────────────────────────────────
with tab_paths:
    if paths_df.empty:
        st.caption("Learning paths start at age 2 (most at 2½). They appear here once a kid "
                   f"is old enough and the sync has run. {SYNC_HINT}")
    else:
        for kid_id in paths_df["kid_id"].unique():
            kp = paths_df[paths_df["kid_id"] == kid_id].sort_values("path_order")
            section_header(kp.iloc[0]["display_name"])
            table = kp[["path_name", "pct_complete", "reached_level_name", "focus_level_name",
                        "latest_evidence_date", "latest_evidence_notes", "evidence_count"]].copy()
            table["reached_level_name"] = table["reached_level_name"].fillna("Not started")
            st.dataframe(
                table, width="stretch", hide_index=True,
                column_config={
                    "path_name": "Path",
                    "pct_complete": st.column_config.ProgressColumn(
                        "Progress", min_value=0, max_value=100, format="%.0f%%"),
                    "reached_level_name": "Reached",
                    "focus_level_name": "Working on",
                    "latest_evidence_date": st.column_config.DateColumn("Last seen", format="MMM D"),
                    "latest_evidence_notes": "Latest note",
                    "evidence_count": st.column_config.NumberColumn("Entries", format="%d"),
                },
            )
            with st.expander("Activities for every path's current level"):
                for _, r in kp.iterrows():
                    acts = [a for a in str(r["focus_activities"] or "").split("\n") if a.strip()]
                    st.markdown(f"**{r['path_name']} · {r['focus_level_name']}**: {r['focus_description']}")
                    st.markdown("\n".join(f"- {a}" for a in acts))
        st.caption("Paths and levels live in `progeny/reference/learning_paths.yaml`.")

# ── Milestones ───────────────────────────────────────────────────────────────
with tab_ms:
    ms_df = mart("mart_progeny_milestones")
    st.caption("CDC *Learn the Signs. Act Early.* checklists: what most children (75% or more) do "
               "by each age. A conversation starter for well-child visits, not a test. "
               "[cdc.gov/act-early](https://www.cdc.gov/act-early/milestones/index.html)")
    unborn = [k["display_name"] for k in KIDS if not k["birthdate"]]
    if unborn:
        st.caption(f"{', '.join(unborn)}: milestones start once the birthdate is in kids.yaml.")
    if ms_df.empty:
        st.caption(f"No checklist yet. {SYNC_HINT}")
    else:
        logged = st.session_state.setdefault("pg_ms_logged", set())
        for kid_id in ms_df["kid_id"].unique():
            km = ms_df[ms_df["kid_id"] == kid_id]
            section_header(f"{km.iloc[0]['display_name']} · {int(km.iloc[0]['age_months'])} months")
            for role, heading in (("current", "Current band"), ("next", "Coming up")):
                band = km[km["band_role"] == role]
                if band.empty:
                    continue
                n_obs = int(band["is_observed"].sum())
                with st.container(border=True):
                    st.markdown(f"**{heading}: {band.iloc[0]['band_label']}**: "
                                f"{n_obs} of {len(band)} observed")
                    for domain_label, items in band.groupby("domain_label", sort=False):
                        st.markdown(f"<div class='pg-kicker'>{esc(domain_label)}</div>",
                                    unsafe_allow_html=True)
                        for _, m in items.iterrows():
                            key = (kid_id, m["milestone_id"])
                            if m["is_observed"]:
                                st.markdown(f"<div class='pg-ms done'>✓ {esc(m['milestone'])} "
                                            f"<small>· {fmt_date(m['observed_date'])}</small></div>",
                                            unsafe_allow_html=True)
                            elif key in logged:
                                st.markdown(f"<div class='pg-ms done'>✓ {esc(m['milestone'])} "
                                            f"<small>· logged, syncs next run</small></div>",
                                            unsafe_allow_html=True)
                            else:
                                c1, c2 = st.columns([10, 1.4])
                                c1.markdown(f"<div class='pg-ms'>○ {esc(m['milestone'])}</div>",
                                            unsafe_allow_html=True)
                                c2.button("Seen it", key=f"ms_{kid_id}_{m['milestone_id']}",
                                          width="stretch", on_click=mark_seen, args=(kid_id, m["milestone_id"]))

# ── Reading ──────────────────────────────────────────────────────────────────
with tab_read:
    rd = mart("mart_progeny_reading")
    if rd.empty or int(rd["total_reads"].sum()) == 0:
        st.caption("No books logged yet. Log each read-aloud with **Quick log → Book**. Re-reads "
                   f"count toward 1,000 Books Before Kindergarten. {SYNC_HINT}")
    else:
        for _, r in rd.iterrows():
            section_header(f"{r['display_name']} · 1,000 Books Before Kindergarten")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Books read", f"{int(r['total_reads']):,}",
                      delta=f"{int(r['unique_titles'])} different titles", delta_color="off", delta_arrow="off", border=True)
            c2.metric("Last 30 days", f"{int(r['reads_last_30d'])}",
                      delta=f"{r['pace_per_day_30d']:.1f} / day", delta_color="off", delta_arrow="off", border=True)
            if pd.notna(r["needed_per_day"]):
                on_pace = r["pace_per_day_30d"] >= r["needed_per_day"]
                c3.metric("Needed pace", f"{r['needed_per_day']:.1f} / day",
                          delta="on pace" if on_pace else "behind pace",
                          delta_color="normal" if on_pace else "inverse", border=True)
                c4.metric("Kindergarten", f"{int(r['days_to_kindergarten'])} days",
                          delta=fmt_date(r["kindergarten_target"]), delta_color="off", delta_arrow="off", border=True)
            st.progress(min(int(r["total_reads"]), 1000) / 1000,
                        text=f"{int(r['total_reads']):,} / 1,000 ({r['pct_to_goal']:.0f}%)")
            kt = titles_df[titles_df["kid_id"] == r["kid_id"]].head(10) if not titles_df.empty else titles_df
            if not kt.empty:
                st.markdown("**Most-read**")
                st.dataframe(
                    kt[["title", "author", "times_read", "last_read"]].fillna({"author": ""}),
                    width="stretch", hide_index=True,
                    column_config={"title": "Title", "author": "Author",
                                   "times_read": st.column_config.NumberColumn("Reads", format="%d"),
                                   "last_read": st.column_config.DateColumn("Last read", format="MMM D")},
                )

# ── Baby prep ────────────────────────────────────────────────────────────────
with tab_prep:
    tasks = mart("mart_progeny_prep_tasks")
    burn = mart("mart_progeny_prep")
    if tasks.empty:
        st.caption(f"No prep tasks yet. Add some with **Quick log → Prep task**. {SYNC_HINT}")
    else:
        n_open = int((tasks["status"] != "done").sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open", n_open, border=True)
        c2.metric("Done", int((tasks["status"] == "done").sum()), border=True)
        c3.metric("Overdue", int((tasks["status"] == "overdue").sum()), border=True)
        due = burn["baby_due_date"].dropna().iloc[0] if not burn.empty and burn["baby_due_date"].notna().any() else None
        if due is not None:
            c4.metric("Due date", fmt_date(due),
                      delta=f"{(pd.Timestamp(due).date() - today).days} days", delta_color="off", delta_arrow="off", border=True)

        if not burn.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=burn["day"], y=burn["ideal_open"], name="Ideal",
                                     mode="lines", line=dict(color="#A9B2AC", dash="dash", width=1)))
            actual = burn[~burn["is_future"]]
            fig.add_trace(go.Scatter(x=actual["day"], y=actual["open_tasks"], name="Open tasks",
                                     mode="lines", line=dict(color="#D97706", width=2, shape="hv")))
            fig.update_layout(
                height=260, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#FAFAFA"), hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.08)", rangemode="tozero", title=None),
            )
            st.plotly_chart(fig, width="stretch")

        done_now = st.session_state.setdefault("pg_prep_done", set())
        for category, items in tasks[tasks["status"] != "done"].groupby("category"):
            st.markdown(f"<div class='pg-kicker'>{esc(category)}</div>", unsafe_allow_html=True)
            for _, t in items.iterrows():
                c1, c2 = st.columns([10, 1.4])
                due_txt = f" · due {fmt_date(t['due_date'])}" if pd.notna(t["due_date"]) else ""
                flag = " ⚠️" if t["status"] == "overdue" else ""
                if t["task_id"] in done_now:
                    c1.markdown(f"<div class='pg-ms done'>✓ {esc(t['task'])} <small>· logged, "
                                f"syncs next run</small></div>", unsafe_allow_html=True)
                    continue
                c1.markdown(f"<div class='pg-ms'>○ {esc(t['task'])}<small>{due_txt}{flag}</small></div>",
                            unsafe_allow_html=True)
                c2.button("Done", key=f"prep_{t['task_id']}", width="stretch",
                          on_click=mark_done, args=(t.to_dict(),))

        done = tasks[tasks["status"] == "done"]
        if not done.empty:
            with st.expander(f"Done ({len(done)})"):
                st.dataframe(done[["task", "category", "done_date"]], width="stretch", hide_index=True,
                             column_config={"task": "Task", "category": "Category",
                                            "done_date": st.column_config.DateColumn("Done", format="MMM D")})

with st.expander("ℹ️ How this works", expanded=False):
    st.markdown("""
    Everything you log is appended to **`data/progeny/*.jsonl`** (local, gitignored, never committed).
    The daily sync loads it with `pipelines/progeny_pipeline.py` and dbt builds the
    `mart_progeny_*` views this page reads. Kids live in `data/progeny/kids.yaml`: rename
    a kid or add a birthdate there. Ages are always computed from the birthdate, never stored.
    """)
