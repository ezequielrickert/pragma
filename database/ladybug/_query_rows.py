"""Narrows `Connection.execute(...)`'s result to the shape every read
path in this package actually gets back.

`lb.Connection.execute` is typed `QueryResult | list[QueryResult]` -
Ladybug returns a `list[QueryResult]` only for a multi-statement query
string (several `;`-separated statements in one call), and every call
site in this package passes exactly one statement. Each row within a
single `QueryResult` is typed `list[Any] | dict[str, Any]` - the `dict`
half only appears once `QueryResult.rows_as_dict()` has been called
(confirmed against `ladybug/query_result.py`), which nothing in this
package ever does, so every row actually reaching a caller here is a
plain positional `list[Any]`.

`rows()` asserts both narrowings instead of re-deriving them at each of
the ~30 call sites that iterate a query result by position
(`row[0]`, tuple-unpacking) - the same "assert the shape you've verified,
don't blanket-ignore it" fix mypy strict calls for repeated in one place.

Details: docs/dev/database/ladybug/_query_rows.md#module
"""
from __future__ import annotations

from typing import Any, Iterator, List

import ladybug as lb


def rows(result: "lb.QueryResult | list[lb.QueryResult]") -> Iterator[List[Any]]:
    """Iterate `result`'s rows as plain `list[Any]` - see module docstring
    for why both narrowings (single `QueryResult`, list-shaped rows) hold
    for every query this package issues.
    Details: docs/dev/database/ladybug/_query_rows.md#rows
    """
    assert isinstance(result, lb.QueryResult), (
        f"expected a single QueryResult, got {type(result)!r} - "
        "did a call site pass a multi-statement query string?"
    )
    for row in result:
        assert isinstance(row, list), (
            f"expected a positional row, got {type(row)!r} - "
            "did a call site turn on QueryResult.rows_as_dict()?"
        )
        yield row
