"""`Screen` write and read path for `LadybugGraphStore` - the semantic
tier's second writer, following `semantic.py::record_entities`'s pattern
(full-rebuild-per-run, `DERIVED_FROM`-provenanced, no-provenance-no-write).
`_LadybugScreenMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)` existing
on whatever it ends up mixed into.

**Deletes are scoped by source label, not blanket.** `DERIVED_FROM` is one
shared rel table declared `FROM Screen TO Page` *and* `FROM Entity TO
Component` *and* `FROM Field TO Component` (`schema.py`) - every
semantic-tier writer's provenance edges live in the same table. Before
this module existed, `record_entities` was the table's only writer, so
its own `MATCH ()-[r:DERIVED_FROM]->() DELETE r` was safe by construction.
Adding a second writer made that blanket delete a bug: whichever pass ran
second would silently erase the first pass's provenance on every run.
`record_screens` here deletes only `Screen`-sourced `DERIVED_FROM` edges
(`MATCH (:Screen)-[r:DERIVED_FROM]->()`); `semantic.py::record_entities`
was updated the same way, scoped to `Entity`/`Field`. `RENDERS` needs no
such scoping - the schema declares it `FROM Screen TO Page` only, so it
has exactly one writer and a blanket delete is unambiguous.

Details: docs/dev/database/ladybug/screen.md#module
"""
from __future__ import annotations

from typing import List, Sequence

import ladybug as lb

from ._mixin_base import _LadybugMixinBase
from ._query_rows import rows as _rows
from core.interfaces import SemanticScreen

# Recorded on every `DERIVED_FROM` edge this module writes.
_GENERATOR = "screens.build_screens"
# A Screen's grouping (which Page it renders) is a deterministic 1:1
# mapping, never a heuristic guess - see screens.py's own module docstring.
_METHOD = "deterministic"
_CONFIDENCE = 1.0


class _LadybugScreenMixin(_LadybugMixinBase):
    """Details: docs/dev/database/ladybug/screen.md#_ladybugscreenmixin"""

    def record_screens(self, screens: Sequence[SemanticScreen], run_id: str = "") -> None:
        """Replace this site's `Screen` set with `screens`.

        A full rebuild, like `record_entities`: a Screen has no stable
        identity across a rebuild that adds, removes or reshapes Pages,
        so patching in place isn't sound.

        Raises:
            ValueError: if any screen has an empty `page_url`. Mirrors
                `record_entities`'s own `derived_from` check - this tier
                is only worth having if every node in it can be traced
                back, and enforcing that at the write is the only place
                the rule cannot be forgotten.
        Details: docs/dev/database/ladybug/screen.md#record_screens
        """
        for screen in screens:
            if not screen.page_url:
                raise ValueError("semantic screen has no page_url derived_from")

        def op(conn: lb.Connection) -> None:
            # Edges first: Ladybug refuses to delete a node that still has
            # relationships attached. Scoped by source label - see this
            # module's own docstring for why DERIVED_FROM can't be a
            # blanket delete here.
            conn.execute("MATCH (:Screen)-[r:DERIVED_FROM]->() DELETE r")
            conn.execute("MATCH ()-[r:RENDERS]->() DELETE r")
            conn.execute("MATCH (s:Screen) DELETE s")

            for screen in screens:
                self._ensure_page(conn, screen.page_url)
                conn.execute(
                    """
                    MATCH (page:Page {url: $page_url})
                    CREATE (s:Screen {name: $name, route_pattern: $route_pattern, purpose: $purpose})
                    CREATE (s)-[:RENDERS]->(page)
                    CREATE (s)-[:DERIVED_FROM {method: $method, confidence: $confidence,
                                                run_id: $run_id, generator: $generator}]->(page)
                    """,
                    {
                        "page_url": screen.page_url, "name": screen.name,
                        "route_pattern": screen.route_pattern, "purpose": screen.purpose,
                        "method": _METHOD, "confidence": _CONFIDENCE,
                        "run_id": run_id, "generator": _GENERATOR,
                    },
                )

        self._call(op)

    def get_screens(self) -> List[SemanticScreen]:
        """Every `Screen` with its rendered `Page`, ordered by `page_url`.

        Rebuilt into the same `SemanticScreen` shape `build_screens`
        produces (before narration), same round-trip property
        `get_entities` maintains for `SemanticEntity`.
        Details: docs/dev/database/ladybug/screen.md#get_screens
        """
        def op(conn: lb.Connection) -> List[SemanticScreen]:
            screen_rows = _rows(conn.execute(
                """
                MATCH (s:Screen)-[:RENDERS]->(page:Page)
                RETURN page.url, s.route_pattern, s.name, s.purpose
                ORDER BY page.url
                """
            ))
            return [
                SemanticScreen(page_url=page_url, route_pattern=route_pattern, name=name, purpose=purpose)
                for page_url, route_pattern, name, purpose in screen_rows
            ]

        return self._call(op)
