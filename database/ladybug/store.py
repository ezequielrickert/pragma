"""`LadybugGraphStore`: connection lifecycle plus the observation/inferred-
tier read+write path for the crawl graph's persistence backend, one
Ladybug database per site. Registered with `GRAPH_STORE_REGISTRY` twice
at the bottom of this module - `"ladybug"` (on disk) and `"memory"`
(in-memory) - so `pragma.yaml`, `cli.py --graph-store` and
`core/wizard.py` keep working with the same two names the retired DuckDB/
in-memory backends answered to.

**One database per site, not one shared file.** `site` was previously the
first argument of all 41 `GraphStore` methods and a column on all 21
DuckDB tables, existing only so one shared database could tell sites
apart - `Engine.from_config` derives exactly one `site` per run and never
varies it. A dedicated database per site removes that argument and that
column entirely: `clear_site()` becomes `reset()` (close, delete, reopen)
instead of 21 `DELETE`s in dependency order, and a run that purges
(`PragmaConfig.fresh`) reclaims disk instead of leaving freed-but-unshrunk
pages behind, the way the retired DuckDB backend's `data/pragma.duckdb`
(42MB, 20-page crawl, 7.4MB WAL) did.

Details: docs/dev/database/ladybug/store.md#module
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Optional

from core.registry import GRAPH_STORE_REGISTRY
from utils.urls import slugify
from .analysis import _LadybugAnalysisMixin
from .clock import now
from .component import _LadybugComponentMixin
from .component_family import _LadybugComponentFamilyMixin
from .containment import _LadybugContainmentMixin
from .named_queries import _LadybugNamedQueriesMixin
from .network import _LadybugNetworkMixin
from .options import _LadybugOptionsMixin
from .page import _LadybugPageMixin
from .raw_query import _LadybugRawQueryMixin
from .search import _LadybugSearchMixin
from .schema import DDL
from .text_content import _LadybugTextContentMixin
from .writer import LadybugWriter

# Where an on-disk site's database lives when config doesn't say
# otherwise - config/pragma.example.yaml documents overriding this via
# graph_stores.ladybug.directory.
_DEFAULT_DIRECTORY = "data/sites"


def _resolve_path(directory: Optional[str], site: str) -> str:
    """Where this site's database lives - `<directory>/<slug(site)>.lbdb`,
    or Ladybug's own in-memory sentinel (`""`) when `directory` is `None`.
    A bare `site` (a host, e.g. `austral.edu.ar`) needs no URL-specific
    slugging, but goes through the same `slugify` every other per-site
    filename in this project does, so a site name containing anything a
    filesystem would reject is handled identically everywhere, not just
    here.
    Details: docs/dev/database/ladybug/store.md#_resolve_path
    """
    if directory is None:
        return ""
    return os.path.join(directory, f"{slugify(site)}.lbdb")


class LadybugGraphStore(
    _LadybugPageMixin, _LadybugComponentMixin, _LadybugTextContentMixin,
    _LadybugComponentFamilyMixin, _LadybugAnalysisMixin, _LadybugNetworkMixin,
    _LadybugOptionsMixin, _LadybugContainmentMixin, _LadybugRawQueryMixin,
    _LadybugNamedQueriesMixin, _LadybugSearchMixin,
):
    """Owns one Ladybug database, scoped to exactly one site.

    All access goes through `self._writer.call(...)`, which runs on one
    dedicated thread - see `writer.py` for why. `site` is stored only to
    write/refresh the `Site` header row and to resolve this store's own
    path; unlike every DuckDB method this replaces, it is never a query
    parameter, since every table already belongs to this site by
    construction. The eleven mixins supply the full read+write path -
    `page.py` (Page/link/edge, and the shared `_ensure_page` helper the
    others call through `self`), `component.py` (Component/Interaction),
    `text_content.py` (TextContent), `component_family.py`
    (ComponentFamily), `analysis.py` (derived graph metrics),
    `network.py` (Request/Endpoint/Payload - the API contract),
    `options.py` (Option), `containment.py` (Container), and the
    retrieval surface split three ways by concern: `raw_query.py`
    (`raw()`, `schema_card()`), `named_queries.py` (the named query
    library and its `query()` dispatcher), `search.py` (FTS) - same
    split-by-concern shape the retired DuckDB backend used, for the same
    file-size reason.
    """

    def __init__(self, site: str, directory: Optional[str] = None) -> None:
        self.site = site
        self.directory = directory
        self.path = _resolve_path(directory, site)
        self._writer: Optional[LadybugWriter] = None

    def connect(self) -> None:
        """Establish the connection, idempotently ensure schema exists,
        and record this site's header row - the one write every other
        write assumes has already happened.
        Details: docs/dev/database/ladybug/store.md#connect
        """
        if self._writer is not None:
            return
        self._writer = LadybugWriter(self.path)
        self._writer.call(lambda conn: conn.execute(DDL))
        self._touch_site()

    def _touch_site(self) -> None:
        """Create this site's `Site` header row if absent, or refresh
        `last_crawled` if present - `first_crawled` is written once and
        never overwritten, the same "first sighting is permanent" rule
        `record_edge`'s `first_seen_run` follows.
        Details: docs/dev/database/ladybug/store.md#_touch_site
        """
        now_value = now()

        def op(conn) -> None:
            conn.execute(
                """
                MERGE (s:Site {name: $name})
                ON CREATE SET s.first_crawled = $now, s.last_crawled = $now
                ON MATCH SET s.last_crawled = $now
                """,
                {"name": self.site, "now": now_value},
            )

        self._call(op)

    def close(self) -> None:
        """Release the connection. Safe to call even if never connected.
        Details: docs/dev/database/ladybug/store.md#close
        """
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def reset(self) -> None:
        """Purge this site's entire graph and start clean - the direct
        replacement for the retired DuckDB backend's `clear_site()`.

        Close, delete the on-disk database (a directory, not a single
        file - confirmed against the real engine, not assumed), reopen.
        A no-op for the in-memory case (`self.path == ""`): there is
        nothing on disk to delete, and a fresh `lb.Database("")` per
        `connect()` call already starts empty.
        Details: docs/dev/database/ladybug/store.md#reset
        """
        self.close()
        if self.path and os.path.exists(self.path):
            if os.path.isdir(self.path):
                shutil.rmtree(self.path)
            else:
                os.remove(self.path)
        self.connect()

    def _call(self, fn):
        if self._writer is None:
            self.connect()
        return self._writer.call(fn)


@GRAPH_STORE_REGISTRY.register("ladybug")
def _build_disk_store(site: str, directory: str = _DEFAULT_DIRECTORY, **_ignored: Any) -> LadybugGraphStore:
    """`graph_store: ladybug` factory - persists to `<directory>/<slug>.lbdb`.
    Details: docs/dev/database/ladybug/store.md#_build_disk_store
    """
    return LadybugGraphStore(site, directory=directory)


@GRAPH_STORE_REGISTRY.register("memory")
def _build_memory_store(site: str, **_ignored: Any) -> LadybugGraphStore:
    """`graph_store: memory` factory - always in-memory, regardless of any
    `directory` a config happens to carry for this name: "memory" means
    "ephemeral," not "on disk with a default path."
    Details: docs/dev/database/ladybug/store.md#_build_memory_store
    """
    return LadybugGraphStore(site, directory=None)
