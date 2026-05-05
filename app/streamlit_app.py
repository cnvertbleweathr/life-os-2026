import duckdb
import streamlit as st

DB_PATH = "data/warehouse/lifeos.duckdb"

st.set_page_config(
    page_title="Life OS",
    page_icon="🧭",
    layout="wide",
)

st.title("Life OS")
st.caption("Personal operating system dashboard")

con = duckdb.connect(DB_PATH, read_only=True)

try:
    healthcheck = con.execute("""
        select *
        from main_marts.mart_lifeos_healthcheck
    """).df()

    goals = con.execute("""
        select *
        from main_marts.mart_goal_inventory
        order by domain
    """).df()

    goal_detail = con.execute("""
    select *
    from main_marts.mart_goal_detail
    order by domain, goal_key
    """).df()

    goal_progress = con.execute("""
    select *
    from main_marts.mart_goal_progress
    order by domain, goal_key
    """).df()

    st.subheader("System Status")
    st.dataframe(healthcheck, use_container_width=True)

    st.subheader("Goal Inventory")
    st.dataframe(goals, use_container_width=True)

    st.subheader("Goal Detail")
    st.dataframe(goal_detail, use_container_width=True)

    st.bar_chart(
        goals.set_index("domain")["goal_count"]
    )

    st.subheader("Goal Progress")
    st.dataframe(goal_progress, use_container_width=True)

finally:
    con.close()
