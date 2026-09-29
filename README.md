# Streamlit caching with CoCo: tutorial companion app

Two versions of the same user-activity dashboard. `before/` is a typical first draft; `after/` is the same file after running all three prompts from the email in CoCo. Both share the same layout and function names, so `diff before/streamlit_app.py after/streamlit_app.py` shows only the fixes. Both generate synthetic data inside Snowflake, so they run on any account with a warehouse.

## Run locally

```bash
cd before   # or after
SNOWFLAKE_DEFAULT_CONNECTION_NAME=<your_connection> python -m streamlit run streamlit_app.py
```

Or paste either `streamlit_app.py` into a new Streamlit app in Snowsight.

Try this: change the Region filter a few times in each version and compare the timing captions.

## Proposed changes (before → after)

### Prompt 1: Stop runaway reruns

> "Refactor these warehouse queries to use @st.cache_data, and convert the filter section into an @st.fragment."

| Function | Added in `after/` | Effect |
|---|---|---|
| `ensure_events_table()` | `@st.cache_resource` | Temp table is built once instead of on every rerun |
| `load_filtered()` | `@st.cache_data(ttl="10m", ...)` | Each filter combination hits the warehouse once |
| `load_mau()` | `@st.cache_data(ttl="10m", ...)` | MAU aggregation runs once per 10 minutes |
| `filtered_section()` | `@st.fragment` | Changing a filter reruns only that section, not the MAU chart |

Watch the "Filter section ran in" and "Full script ran in" captions.

### Prompt 2: Defend against edge cases

> "Audit this app as an unsupervised stakeholder. What breaks if a filter returns 0 rows or if a column has unexpected nulls?"

What CoCo should find in `before/`:
- Clearing a multiselect gives 0 rows, and "Avg revenue per event" shows `$nan`.
- About 5% of rows have a `NULL` region. The `WHERE` clause silently drops them, so the totals look complete but aren't.

Fixes in `after/`:
- A warning when a multiselect is empty, returned before any query runs.
- `st.info` for 0-row results instead of `$nan` metrics.
- `COALESCE(REGION, 'Unknown')`, a selectable "Unknown" option, and a caption counting those rows.
- `fillna(0)` on revenue before aggregating; empty-MAU guard.

### Prompt 3: Automate the SQL layer

> "Write a Snowpark query for this table that aggregates monthly active users, and feed it directly into an st.bar_chart."

| Before | After |
|---|---|
| `table(...).to_pandas()` pulls all ~200k rows, then `groupby(...).nunique()` | Snowpark `date_trunc` → `group_by` → `count_distinct`, run in the warehouse |
| ~200k rows transferred | ~12 rows transferred |
