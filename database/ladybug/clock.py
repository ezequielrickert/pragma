"""One `now()`, shared by every module in this package that stamps a
`TIMESTAMP` column - `store.py` (`Site.first_crawled`/`last_crawled`),
`observation.py` (`Page.visited_at`, `NAVIGATES_TO.created_at`), and
every later step that adds one. Its own module rather than living in
`store.py`: `observation.py` needs it too, and `store.py` imports
`observation.py`'s mixin class, so defining it there would be a circular
import.

Details: docs/dev/database/ladybug/clock.md#module
"""
from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    """A real `datetime`, not an ISO string - Ladybug's `TIMESTAMP` columns
    (unlike DuckDB's TEXT-stored timestamps this replaces) bind a Python
    `datetime` object directly and reject a string with no implicit cast,
    confirmed against the real engine.
    Details: docs/dev/database/ladybug/clock.md#now
    """
    return datetime.now(timezone.utc)
