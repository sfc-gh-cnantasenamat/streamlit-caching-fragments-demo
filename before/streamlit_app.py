"""BEFORE: a first-draft app with the problems from the email.

  1. Runaway reruns: no caching and no fragment, so every widget click
     rereads the CSV and reruns the whole script.
  2. Edge cases: empty filters show $nan, and rows with no region are
     silently dropped from the totals.
"""

import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="User Activity (before)", layout="wide")

# 200k synthetic events; about 5% have no REGION.
DATA_PATH = Path(__file__).parent.parent / "data" / "user_events.csv"

def load_events() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH, parse_dates=["EVENT_DATE"])


def load_filtered(regions: tuple[str, ...], channels: tuple[str, ...]) -> pd.DataFrame:
    df = load_events()
    return df[df["REGION"].isin(regions) & df["CHANNEL"].isin(channels)]


def load_mau() -> pd.DataFrame:
    df = load_events()
    month = df["EVENT_DATE"].dt.to_period("M").dt.to_timestamp()
    return (
        df.groupby(month)["USER_ID"].nunique()
        .rename("MAU").rename_axis("MONTH").reset_index()
    )


st.title("User activity dashboard")
st.caption("Before: no caching, no fragment, no edge-case handling.")

# Clears Streamlit's caches so the timing test can be repeated from cold.
if st.button("Reset cache", icon=":material/restart_alt:"):
    st.cache_data.clear()
    st.session_state.pop("run_log", None)
    st.rerun()

run_start = time.perf_counter()
st.session_state["full_run"] = True


def render_chart() -> None:
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

    revenue = df["REVENUE"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Events", f"{len(df):,}")
    c2.metric("Revenue", f"${revenue.sum():,.0f}")
    c3.metric("Avg revenue per event", f"${revenue.mean():,.2f}")

    render_chart()
    st.dataframe(df.head(100), hide_index=True)


def filtered_section() -> None:
    start = run_start if st.session_state.get("full_run") else time.perf_counter()
    show_filtered_data()
    render_timing(start)


st.subheader("Input")
filtered_section()
