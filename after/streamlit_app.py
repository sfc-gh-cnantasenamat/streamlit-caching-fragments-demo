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


def generate_events() -> pd.DataFrame:
    """Rebuild the same seeded dataset if the CSV is missing or unreadable."""
    import numpy as np

    rng = np.random.default_rng(42)
    n = 200_000
    today = pd.Timestamp("2026-09-29")
    df = pd.DataFrame({
        "EVENT_DATE": today - pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
        "USER_ID": ["user_%d" % i for i in rng.integers(1, 2001, n)],
        "REGION": rng.choice(["AMER", "EMEA", "APJ"], n),
        "CHANNEL": rng.choice(["web", "mobile", "api"], n),
        "REVENUE": rng.integers(1, 501, n),
    })
    df.loc[rng.random(n) < 0.05, "REGION"] = None
    return df


def snowflake_session():
    """Return the app's Snowpark session in Streamlit in Snowflake, else None.

    Locally and on Community Cloud this returns None, so the app reads the
    bundled CSV and needs no Snowflake credentials.
    """
    try:
        # Container runtime: the SPCS service mounts a session token here.
        if Path("/snowflake/session/token").exists():
            return st.connection("snowflake").session()
        # Warehouse runtime: Snowpark provides the active session.
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        return None


@st.cache_data(show_spinner="Loading events...")
def load_events() -> pd.DataFrame:
    session = snowflake_session()
    if session is not None:
        df = session.sql(
            "SELECT EVENT_DATE, USER_ID, REGION, CHANNEL, REVENUE FROM USER_EVENTS_DEMO"
        ).to_pandas()
        df["EVENT_DATE"] = pd.to_datetime(df["EVENT_DATE"])
        return df
    try:
        return pd.read_csv(DATA_PATH, parse_dates=["EVENT_DATE"])
    except (FileNotFoundError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return generate_events()



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


def render_chart() -> None:
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
    st.subheader("Data")
    c1, c2, c3 = st.columns(3)
    c1.metric("Events", f"{len(df):,}")
    c2.metric("Revenue", f"${revenue.sum():,.0f}")
    c3.metric("Avg revenue per event", f"${revenue.mean():,.2f}")

    unknown = (df["REGION"] == UNKNOWN_REGION).sum()
    if unknown:
        st.caption(f"{unknown:,} events have no region and are shown as '{UNKNOWN_REGION}'.")

    render_chart()
    st.dataframe(df.head(100), hide_index=True)


@st.fragment
def filtered_section() -> None:
    start = run_start if st.session_state.get("full_run") else time.perf_counter()
    show_filtered_data()
    render_timing(start)


st.subheader("Input")
filtered_section()
