"""`LadybugGraphStore`: connection lifecycle for the crawl graph's
persistence backend, one Ladybug database per site.

Storage-migration plan phase 3 (see the plan under
`docs/dev/database/ladybug/store.md#storage-migration-plan` for the full
rationale) - this module owns only what step 3 of that plan scopes to it:
opening/closing/resetting the database and writing the one-row `Site`
header. The ~15 write methods `GraphStoreSink` calls and the read/query
surface land in `network.py`/`semantic.py`/`queries.py` as later steps
fill them in; `LadybugGraphStore` does not yet implement the `GraphStore`
ABC (`core/interfaces.py`) and is not yet registered with
`GRAPH_STORE_REGISTRY` - both happen once the write/read path exists,
so an incomplete implementation is never reachable from `pragma.yaml`.

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
from datetime import datetime, timezone
from typing import Optional

from utils.urls import slugify
from .schema import DDL
from .writer import LadybugWriter


def _now() -> datetime:
    """A real `datetime`, not an ISO string - Ladybug's `TIMESTAMP` columns
    (unlike DuckDB's TEXT-stored timestamps this replaces) bind a Python
    `datetime` object directly and reject a string with no implicit cast,
    confirmed against the real engine. Every `TIMESTAMP` write in this
    package goes through this function so none of them drift back to a
    string by habit.
    Details: docs/dev/database/ladybug/store.md#_now
    """
    return datetime.now(timezone.utc)


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


class LadybugGraphStore:
    """Owns one Ladybug database, scoped to exactly one site.

    All access goes through `self._writer.call(...)`, which runs on one
    dedicated thread - see `writer.py` for why. `site` is stored only to
    write/refresh the `Site` header row and to resolve this store's own
    path; unlike every DuckDB method this replaces, it is never a query
    parameter, since every table already belongs to this site by
    construction.
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
        now = _now()

        def op(conn) -> None:
            conn.execute(
                """
                MERGE (s:Site {name: $name})
                ON CREATE SET s.first_crawled = $now, s.last_crawled = $now
                ON MATCH SET s.last_crawled = $now
                """,
                {"name": self.site, "now": now},
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
