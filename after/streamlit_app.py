"""AFTER: the same app with the CoCo caching prompts applied.

  1. Stop runaway reruns: data loads cached with @st.cache_data,
     filter section isolated in an @st.fragment.
  2. Edge cases: empty selections, 0-row results, and missing regions
     are handled explicitly.
"""

import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="User Activity (after)", layout="wide")

# 200k synthetic events; about 5% have no REGION.
DATA_PATH = Path(__file__).parent.parent / "data" / "user_events.csv"

UNKNOWN_REGION = "Unknown"


@st.cache_data(show_spinner="Loading events...")
def load_events() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH, parse_dates=["EVENT_DATE"])


@st.cache_data(show_spinner="Filtering events...")
def load_filtered(regions: tuple[str, ...], channels: tuple[str, ...]) -> pd.DataFrame:
    df = load_events().assign(REGION=lambda d: d["REGION"].fillna(UNKNOWN_REGION))
    return df[df["REGION"].isin(regions) & df["CHANNEL"].isin(channels)]


@st.cache_data(show_spinner="Aggregating monthly active users...")
def load_mau() -> pd.DataFrame:
    df = load_events()
    month = df["EVENT_DATE"].dt.to_period("M").dt.to_timestamp()
    return (
        df.groupby(month)["USER_ID"].nunique()
        .rename("MAU").rename_axis("MONTH").reset_index()
    )


st.title("User activity dashboard")
st.caption("After: cached data loads, fragment-scoped filters, edge cases handled.")

# Clears Streamlit's caches so the timing test can be repeated from cold.
if st.button("Reset cache", icon=":material/restart_alt:"):
    st.cache_data.clear()
    st.session_state.pop("run_log", None)
    st.rerun()

run_start = time.perf_counter()
st.session_state["full_run"] = True

# Inputs are shown above the chart, but the chart code runs first so a
# full run's timing (logged at the end of the filter section) includes it.
input_area = st.container()
chart_area = st.container()

with chart_area:
    st.subheader("Monthly active users")
    mau = load_mau()
    if mau.empty:
        st.info("No activity data yet.")
    else:
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
    regions = col_a.multiselect(
        "Region", ["AMER", "EMEA", "APJ", UNKNOWN_REGION], default=["AMER"]
    )
    channels = col_b.multiselect("Channel", ["web", "mobile", "api"], default=["web"])

    # Guard against empty selections before loading anything.
    if not regions or not channels:
        st.warning("Pick at least one region and one channel.")
        return

    df = load_filtered(tuple(sorted(regions)), tuple(sorted(channels)))

    # 0-row results get a clear message instead of nan metrics.
    if df.empty:
        st.info("No events match these filters.")
        return

    revenue = df["REVENUE"].fillna(0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Events", f"{len(df):,}")
    c2.metric("Revenue", f"${revenue.sum():,.0f}")
    c3.metric("Avg revenue per event", f"${revenue.mean():,.2f}")

    unknown = (df["REGION"] == UNKNOWN_REGION).sum()
    if unknown:
        st.caption(f"{unknown:,} events have no region and are shown as '{UNKNOWN_REGION}'.")

    st.dataframe(df.head(100), hide_index=True)


@st.fragment
def filtered_section() -> None:
    start = run_start if st.session_state.get("full_run") else time.perf_counter()
    show_filtered_data()
    render_timing(start)


with input_area:
    st.subheader("Input")
    filtered_section()
