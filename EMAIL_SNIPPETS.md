# Email campaign: code snippets and CoCo prompt

Companion content for the "Quick tip for Streamlit caching in CoCo" email. The snippets are trimmed from `after/streamlit_app.py` (timing and edge-case code left out) so they fit in an email.

## Fix the app with CoCo

Open `before/streamlit_app.py` in Cortex Code (or Snowsight), select the whole file, and give CoCo this prompt:

> Refactor this Streamlit app so filter clicks don't redo expensive work:
> 1. Wrap `load_events`, `load_filtered`, and `load_mau` in `@st.cache_data`.
> 2. Turn `filtered_section` into an `@st.fragment` so changing a filter reruns only that section.
> 3. Handle edge cases: warn when a filter is empty, show a message instead of `$nan` when 0 rows come back, and keep rows with a missing region visible as "Unknown" instead of dropping them.

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

From a headless test of the demo apps (CSV data, one test, not a benchmark):

| | Before | After |
|---|---|---|
| Avg rerun | ~0.18s | ~0.01s |

Against a warehouse the gap is larger, because each uncached rerun is a round trip to Snowflake. In an earlier Snowflake-backed version of this demo, reruns averaged 1.78s before and 0.18s after, and repeat filter picks took about 0.01s.

## Notes

- The email snippets show a Snowflake query, which matches the email's audience. The demo repo reads a CSV instead so it runs anywhere without credentials; the caching and fragment pattern is the same.
- The snippets drop the tuple sorting and empty-filter guards from the full app. Full code: https://github.com/sfc-gh-cnantasenamat/streamlit-caching-fragments-demo
- The email says "Highlight your query code" before prompting CoCo. Snippet 1 is the natural code to highlight in that screenshot.
