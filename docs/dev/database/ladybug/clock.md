# database/ladybug/clock.py

## module

One `now()`, shared by every module in this package that stamps a `TIMESTAMP`
column - `store.py` (`Site.first_crawled`/`last_crawled`), `page.py`
(`Page.visited_at`, `NAVIGATES_TO.created_at`), `network.py`
(`Request.observed_at`).

Its own module rather than living in `store.py`, for a concrete reason:
`page.py` needs it too, and `store.py` imports `page.py`'s mixin class, so
defining it in `store.py` would be a circular import. A one-function module
looks like over-splitting until you try the alternative.

## now

Returns a real `datetime`, not an ISO string.

Ladybug's `TIMESTAMP` columns bind a Python `datetime` directly and **reject a
string with no implicit cast** - confirmed against the real engine. The retired
DuckDB backend stored timestamps as TEXT and took strings, so this is one of
the small places where a port that looked mechanical was not, and where copying
the old call sites verbatim would have failed at runtime rather than at import.

UTC, always. A crawl's timestamps are compared across runs and machines, and a
local-time stamp makes `first_seen_run`-style reasoning wrong twice a year.
