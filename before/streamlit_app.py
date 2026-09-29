"""BEFORE: a first-draft app with the three problems from the email.

  1. Runaway reruns: no caching and no fragment, so every widget click
     reruns the whole script and every warehouse query.
  2. Edge cases: empty filters show $nan, and NULL regions are silently
     dropped from the totals.
  3. SQL layer: monthly active users is computed in pandas after pulling
     every row out of the warehouse.
"""

import json
import os
import time

import streamlit as st

st.set_page_config(page_title="User Activity (before)", layout="wide")

# Locally, set SNOWFLAKE_DEFAULT_CONNECTION_NAME to pick a connections.toml entry.
conn = st.connection("snowflake")

EVENTS_TABLE = "USER_EVENTS_DEMO"

# Synthetic event log, materialized once as a temp table so every query
# (pandas and Snowpark) reads the same rows.
EVENTS_SQL = f"""
CREATE TEMPORARY TABLE IF NOT EXISTS {EVENTS_TABLE} AS
SELECT
    DATEADD('day', -UNIFORM(0, 364, RANDOM()), CURRENT_DATE())      AS EVENT_DATE,
    'user_' || UNIFORM(1, 2000, RANDOM())                             AS USER_ID,
    CASE WHEN UNIFORM(1, 20, RANDOM()) = 1 THEN NULL
         ELSE ARRAY_CONSTRUCT('AMER','EMEA','APJ')[UNIFORM(0, 2, RANDOM())]::STRING
    END                                                               AS REGION,
    ARRAY_CONSTRUCT('web','mobile','api')[UNIFORM(0, 2, RANDOM())]::STRING AS CHANNEL,
    ROUND(UNIFORM(1, 500, RANDOM()) * 1.0, 2)                         AS REVENUE
FROM TABLE(GENERATOR(ROWCOUNT => 200000))
"""


def ensure_events_table() -> None:
    """Create the demo table."""
    # Turn off Snowflake's result cache so only Streamlit caching speeds up reruns.
    conn.session().sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
    conn.session().sql(EVENTS_SQL).collect()


def load_filtered(regions: tuple[str, ...], channels: tuple[str, ...]):
    sql = f"""
        SELECT EVENT_DATE, USER_ID, REGION, CHANNEL, REVENUE
        FROM {EVENTS_TABLE}
        WHERE ARRAY_CONTAINS(REGION::VARIANT, PARSE_JSON(?))
          AND ARRAY_CONTAINS(CHANNEL::VARIANT, PARSE_JSON(?))
    """
    return conn.session().sql(
        sql, params=[json.dumps(list(regions)), json.dumps(list(channels))]
    ).to_pandas()


# Pulls every row into pandas, then counts distinct users per month client-side.
def load_mau():
    df = conn.session().table(EVENTS_TABLE).to_pandas()
    df["MONTH"] = df["EVENT_DATE"].astype("datetime64[ns]").dt.to_period("M").dt.to_timestamp()
    return df.groupby("MONTH", as_index=False)["USER_ID"].nunique().rename(columns={"USER_ID": "MAU"})


run_start = time.perf_counter()
ensure_events_table()

st.title("User activity dashboard")
st.caption("Before: no caching, no fragment, no edge-case handling.")

# Clears Streamlit's caches so the timing test can be repeated from cold.
if st.button("Reset cache", icon=":material/restart_alt:"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state.pop("run_log", None)
    st.rerun()

st.session_state["full_run"] = True

# Inputs are shown above the chart, but the chart code runs first so a
# full run's timing (logged at the end of the filter section) includes it.
input_area = st.container()
chart_area = st.container()

with chart_area:
    st.subheader("Monthly active users")
    mau = load_mau()
    st.bar_chart(mau, x="MONTH", y="MAU")


def render_timing(start: float) -> None:
    """Log this run's duration and show first run vs. reruns."""
    # A full script run sets this flag; a fragment-only rerun does not.
    kind = "Full script" if st.session_state.pop("full_run", False) else "Fragment only"
    log = st.session_state.setdefault("run_log", [])
    log.append({"Run": len(log) + 1, "Scope": kind, "Seconds": round(time.perf_counter() - start, 3)})

    first = log[0]["Seconds"]
    reruns = [r["Seconds"] for r in log[1:]]
    st.subheader("Run timing")
    t1, t2, t3 = st.columns(3)
    t1.metric("First run", f"{first:.2f}s")
    if reruns:
        avg = sum(reruns) / len(reruns)
        t2.metric("Avg rerun", f"{avg:.2f}s", delta=f"{avg - first:+.2f}s vs first", delta_color="inverse")
        t3.metric("Rerun speedup", f"{first / avg:.1f}x" if avg else "n/a")
    else:
        t2.metric("Avg rerun", "n/a")
        t3.metric("Rerun speedup", "n/a")
        st.caption("Change a filter to record a rerun.")
    st.dataframe(log[::-1], hide_index=True)


def show_filtered_data() -> None:
    col_a, col_b = st.columns(2)
    regions = col_a.multiselect("Region", ["AMER", "EMEA", "APJ"], default=["AMER"])
    channels = col_b.multiselect("Channel", ["web", "mobile", "api"], default=["web"])

    df = load_filtered(tuple(sorted(regions)), tuple(sorted(channels)))

    c1, c2, c3 = st.columns(3)
    c1.metric("Events", f"{len(df):,}")
    c2.metric("Revenue", f"${df['REVENUE'].sum():,.0f}")
    c3.metric("Avg revenue per event", f"${df['REVENUE'].mean():,.2f}")

    st.dataframe(df.head(100), hide_index=True)


def filtered_section() -> None:
    start = run_start if st.session_state.get("full_run") else time.perf_counter()
    show_filtered_data()
    render_timing(start)


with input_area:
    st.subheader("Input")
    filtered_section()
