"""Primary keys for node tables Ladybug has no secondary index for -
Kùzu/Ladybug hash-indexes the primary key only, so any property a write
path upserts on has to be the key itself or every upsert is a table scan
(docs/dev/database/ladybug/ids.md discusses the two backends this was
checked against).

`Component`/`Container` are content-derived and page-decoupled (issue
#134): two instances discovered on different pages `MERGE` onto the same
row the moment every field that stays on the node (`schema.py`'s
`DESCRIPTIVE_COMPONENT_FIELDS`/`CONTAINER_DESCRIPTIVE_FIELDS`) matches
exactly - the ordinary primary-key MERGE this database already does for
`Page`/`Site`, not a new mechanism. This is the strict, no-judgment floor
collapse gets for free: a byte-identical navbar on every page becomes one
row with zero similarity computation. Genuinely *similar*-but-not-
identical instances (a variant, a near-duplicate with one differing
class) are a fuzzy question this hash cannot and does not answer - that's
the leaf/composite vector matching pipeline's job (issues #131/#132),
layered on top of this floor once it exists, not a replacement for it.

Never Python's built-in `hash()` here - process-randomized by
`PYTHONHASHSEED`, not reproducible across runs (`hashlib.sha1` is,
deterministic by design).

Details: docs/dev/database/ladybug/ids.md#module
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable

from .schema import CONTAINER_DESCRIPTIVE_FIELDS, DESCRIPTIVE_COMPONENT_FIELDS


def _content_hash(values: Iterable[Any]) -> str:
    joined = "\x1f".join(str(v) for v in values)
    return hashlib.sha1(joined.encode()).hexdigest()


def component_content_id(fields: Dict[str, Any]) -> str:
    """`Component`'s primary key - a hash of every field ordered by
    `DESCRIPTIVE_COMPONENT_FIELDS`, the exact set that stays on the node.
    `fields` missing a name reads as `""`, the same "absence is itself a
    shared trait" rule the leaf feature vector (#131) uses for the same
    reason: a caller that only knows a component by its path (no facts
    yet) still gets a real, reproducible id - the shared blank-content one
    every such caller collides onto, documented in `component.py`.
    Details: docs/dev/database/ladybug/ids.md#component_content_id
    """
    ordered = (fields.get(name, "") for name in DESCRIPTIVE_COMPONENT_FIELDS)
    return f"component:{_content_hash(ordered)}"


def container_content_id(fields: Dict[str, Any]) -> str:
    """`Container`'s primary key - same scheme as `component_content_id`,
    over `CONTAINER_DESCRIPTIVE_FIELDS`.
    Details: docs/dev/database/ladybug/ids.md#container_content_id
    """
    ordered = (fields.get(name, "") for name in CONTAINER_DESCRIPTIVE_FIELDS)
    return f"container:{_content_hash(ordered)}"


def endpoint_id(method: str, host: str, path_pattern: str) -> str:
    """`Endpoint`'s own primary key - `"METHOD host/path/{id}"`. Built from
    exactly the fields every observation of the same logical endpoint
    shares, so two `Request`s for the same call always `MERGE` onto one
    `Endpoint` node regardless of which specific ids their URLs carried.
    Details: docs/dev/database/ladybug/ids.md#endpoint_id
    """
    return f"{method} {host}{path_pattern}"
