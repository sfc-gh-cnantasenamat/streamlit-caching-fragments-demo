# Email campaign: code snippets and CoCo prompt

Companion content for the "Quick tip for Streamlit caching in CoCo" email. The snippets are trimmed from `after/streamlit_app.py` (timing and edge-case code left out) so they fit in an email.

## Fix the app with CoCo

Open `before/streamlit_app.py` in Snowsight (or Cortex Code), select the whole file, and give CoCo this prompt:

> Refactor this Streamlit app so filter clicks don't rerun heavy warehouse queries:
> 1. Wrap `load_filtered` and `load_mau` in `@st.cache_data(ttl="10m")`, and wrap `ensure_events_table` in `@st.cache_resource`.
> 2. Turn `filtered_section` into an `@st.fragment` so changing a filter reruns only that section.
> 3. Handle edge cases: warn when a filter is empty, show a message instead of `$nan` when 0 rows come back, and keep NULL regions visible as "Unknown" instead of dropping them.
> 4. Rewrite `load_mau` as a Snowpark aggregation (`date_trunc` by month, `count_distinct` on `USER_ID`) so only the monthly totals leave the warehouse.

CoCo shows the changes as an inline diff. Review the diff and accept it, and the result should match `after/streamlit_app.py`. Run `diff before/streamlit_app.py after/streamlit_app.py` to compare.

If you only want the caching fix, the one-line prompt from the email is enough:

> Refactor these warehouse queries to use @st.cache_data, and convert the filter section into an @st.fragment.

## Snippet 1: Cache the warehouse query

```diff
+ @st.cache_data(ttl="10m")
  def load_filtered(regions, channels):
      return conn.session().sql(
          """SELECT EVENT_DATE, USER_ID, REGION, CHANNEL, REVENUE
             FROM USER_EVENTS_DEMO
             WHERE ARRAY_CONTAINS(REGION::VARIANT, PARSE_JSON(?))
               AND ARRAY_CONTAINS(CHANNEL::VARIANT, PARSE_JSON(?))""",
          params=[json.dumps(regions), json.dumps(channels)],
      ).to_pandas()
```

*The filter values become the cache key, so each combination hits the warehouse once. Repeat clicks return from memory.*

## Snippet 2: Isolate the filters in a fragment

```diff
+ @st.fragment
  def filtered_section():
      col_a, col_b = st.columns(2)
      regions = col_a.multiselect("Region", ["AMER", "EMEA", "APJ"])
      channels = col_b.multiselect("Channel", ["web", "mobile", "api"])

      df = load_filtered(tuple(regions), tuple(channels))
      st.metric("Events", f"{len(df):,}")
      st.dataframe(df)

  filtered_section()
```

*Changing a filter reruns only this function, so the rest of the page (like the monthly active users chart) doesn't run again.*

## Supporting stat

From a headless test run on synthetic data (one test, not a benchmark):

| | Before | After |
|---|---|---|
| Avg rerun | 1.78s | 0.18s |
| Repeat filter pick | ~1.6 to 2.1s | ~0.01s |

Suggested line: "Repeat filter clicks went from ~1.8s to ~0.01s."

## Notes

- The snippets drop the tuple sorting and empty-filter guards from the full app. Link to the repo for the complete version.
- The email says "Highlight your query code" before prompting CoCo. Snippet 1 is the natural code to highlight in that screenshot.
