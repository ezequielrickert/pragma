"""Composite primary keys for node tables Ladybug has no secondary index
for - Kùzu/Ladybug hash-indexes the primary key only, so any property a
write path upserts on has to be the key itself or every upsert is a table
scan (docs/dev/database/ladybug/ids.md discusses the two backends this
was checked against). `Component`/`Container`/`TextContent` are all
upserted by `(page_url, path)`, never by `page_url` or `path` alone, so
that pair is the key - built in exactly one place so every write and
every read agrees on its shape.

`path` here is a CSS selector (`discover_components.js`'s `gp()`), not a
URL path - `body > header > div:nth-of-type(2) > a`. Neither a selector
nor a `route_shape`d URL contains a literal `|`, so it is a safe,
human-readable separator; a component's id is legible in a query result
without decoding, which a hash would not be.

Details: docs/dev/database/ladybug/ids.md#module
"""
from __future__ import annotations

_COMPONENT_ID_SEPARATOR = "|"


def component_id(page_url: str, path: str) -> str:
    """The primary key `Component`/`Container`/`TextContent` all share.
    Details: docs/dev/database/ladybug/ids.md#component_id
    """
    return f"{page_url}{_COMPONENT_ID_SEPARATOR}{path}"


def split_component_id(component_id_value: str) -> tuple[str, str]:
    """Inverse of `component_id` - `(page_url, path)`. Only `HAS_COMPONENT`/
    `HAS_TEXT`/`CONTAINS` traversal results need this; a fresh write never
    does, since it already has `page_url` and `path` as separate arguments.
    Details: docs/dev/database/ladybug/ids.md#split_component_id
    """
    page_url, _, path = component_id_value.partition(_COMPONENT_ID_SEPARATOR)
    return page_url, path


def endpoint_id(method: str, host: str, path_pattern: str) -> str:
    """`Endpoint`'s own primary key - `"METHOD host/path/{id}"`. Built from
    exactly the fields every observation of the same logical endpoint
    shares, so two `Request`s for the same call always `MERGE` onto one
    `Endpoint` node regardless of which specific ids their URLs carried.
    Details: docs/dev/database/ladybug/ids.md#endpoint_id
    """
    return f"{method} {host}{path_pattern}"
