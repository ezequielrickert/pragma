"""Shared component-id resolution for write paths that only have
`(page_url, path)` in hand, not a component's full descriptive facts -
`options.py`, `containment.py`, `state_styles.py`, `semantic.py`, and
`network.py` all write auxiliary data (an `Option`, a `CONTAINS` edge, a
`StateStyle`, provenance, a triggered `Request`) for a component
`component.py`'s `record_component(s)` almost always already wrote,
known at these call sites only by where it sits, not by its content.

Resolves through `HAS_COMPONENT`'s own `path` property - the one place
`(page_url, path)` still identifies a specific rendered instance now that
`Component.id` is content-derived and page-decoupled (issue #134). A path
with no matching edge yet falls back to `stub_component_id(page_url, path)`,
**not** a shared blank-content hash: two different not-yet-discovered
elements on the same page (a stepper's representative, a still-collapsed
dropdown's trigger) would otherwise collide onto the one row a single
shared fallback names, each write silently clobbering whatever the
previous one had just attached to it - confirmed the hard way, this is
exactly what broke `test_stepper_detected_in_a_revealed_snapshot_not_just_
the_initial_one` before this file scoped the fallback per (page_url, path).
Real crawls always discover a component before writing anything auxiliary
about it (see `component.py::record_component_interaction`'s own
docstring on this same fallback), so the stub is reconciled moments later
anyway: `record_component(s)`'s own rediscovery-continuity rule (same
file) finds this exact stub through its `HAS_COMPONENT` edge and updates
it in place once the real content arrives, rather than minting a second
row.

Details: docs/dev/database/ladybug/component.md#_component_lookup
"""
from __future__ import annotations

import hashlib
from typing import Dict, Iterable


def stub_component_id(page_url: str, path: str) -> str:
    """The id a `(page_url, path)` with no `HAS_COMPONENT` edge yet falls
    back to - deterministic and scoped to that one slot, distinct from
    `ids.py::component_content_id`'s `"component:"` prefix so a stub can
    never collide with a real content hash.
    Details: docs/dev/database/ladybug/component.md#stub_component_id
    """
    digest = hashlib.sha1(f"{page_url}\x1f{path}".encode()).hexdigest()
    return f"stub:{digest}"


def resolve_component_ids(conn, page_url: str, paths: Iterable[str]) -> Dict[str, str]:
    """`{path: component_id}` for every given path with a `HAS_COMPONENT`
    edge on this page already. A path missing from the result has none
    yet - callers fall back to `stub_component_id(page_url, path)`
    themselves.
    Details: docs/dev/database/ladybug/component.md#resolve_component_ids
    """
    paths = list(paths)
    if not paths:
        return {}
    rows = conn.execute(
        """
        MATCH (page:Page {url: $page_url})-[e:HAS_COMPONENT]->(c:Component)
        WHERE e.path IN $paths
        RETURN e.path, c.id
        """,
        {"page_url": page_url, "paths": paths},
    )
    return {path: component_id for path, component_id in rows}
