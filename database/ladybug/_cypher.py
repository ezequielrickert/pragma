"""Cypher `SET`-clause building, shared by every mixin whose batched
(`UNWIND`) writes touch a numeric column that can be uniformly `None`
across one batch - the fix below belongs in one place all of them import
rather than repeated inline per mixin.

Details: docs/dev/database/ladybug/_cypher.md#module
"""
from __future__ import annotations

from typing import Sequence

# Geometry fields whose DOUBLE column can't be left to plain type
# inference in a batched (UNWIND) write - confirmed against the real
# engine: when every row in one UNWIND batch has the same field set to
# `None` (a page with no components sized yet, or none at all), Ladybug
# infers that column as STRING rather than DOUBLE and the write fails
# with "Expression STRUCT_EXTRACT(r,x) has data type STRING but expected
# DOUBLE" - a single scalar `None` bound outside a batch has no such
# issue, only a batch column that happens to be uniformly null. An
# explicit `CAST(r.field AS DOUBLE)` sidesteps it in both directions
# (null stays null, a real value still round-trips).
_DOUBLE_FIELDS = frozenset({"x", "y", "width", "height"})

# Same bug, same fix, INT64 columns: a batch of Requests that all failed
# before a status arrived (or all landed with no measurable latency) hits
# the identical all-None-in-one-batch misinference - see analysis.py's
# `record_page_metrics`, which hit this on `click_depth` before this
# module had an `_INT_FIELDS` case at all.
_INT_FIELDS = frozenset({"status", "latency_ms"})


def set_clause(node_alias: str, fields: Sequence[str], row_alias: str = "$") -> str:
    """`"c.tag = $tag, c.x = CAST($x AS DOUBLE), ..."` (or `r.` in place
    of `$` for an `UNWIND` row) - every descriptive `SET` clause in this
    package, single-item and batched alike, builds from this so the
    all-None-batch cast rule above is applied in exactly one place.
    Details: docs/dev/database/ladybug/_cypher.md#set_clause
    """
    parts = []
    for field in fields:
        value = f"{row_alias}{field}" if row_alias != "$" else f"${field}"
        if field in _DOUBLE_FIELDS:
            value = f"CAST({value} AS DOUBLE)"
        elif field in _INT_FIELDS:
            value = f"CAST({value} AS INT64)"
        parts.append(f"{node_alias}.{field} = {value}")
    return ", ".join(parts)
