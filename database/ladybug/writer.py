"""Single-writer-thread serialization for `LadybugGraphStore` - port of
`database/_duckdb_writer.py::DuckDBWriter`, same constraint and same fix.

Ladybug permits exactly one writer per database, and (like DuckDB) a
single connection isn't safe to share across threads without
serialization. The crawl reaches storage from N async workers via
`asyncio.to_thread` (`spiders/orchestration/graph_sink/sink.py::_write`),
i.e. real OS threads calling in at once. `LadybugWriter` is the fix: one
dedicated thread owns the only connection, every caller's Cypher runs as
a closure submitted to it and blocks for the result - callers never touch
`ladybug.Connection` directly, so there is no second code path that could
reach the connection from another thread.

Details: docs/dev/database/ladybug/writer.md#module
"""
from __future__ import annotations

import os
import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable, Optional

import ladybug as lb

from .site_lock import SiteLock

# Ladybug's own docstring for `buffer_pool_size` names this: left at its
# default (0), a `Database` reserves ~8TB of virtual address space via
# mmap, "to get around... the default 8TB mmap address space limit some
# environment [sic]... will be removed once we implement a better
# solution later." One instance is harmless; macOS caps a process at
# ~128TB of user address space, and this project opens one
# `LadybugGraphStore` per site plus one per test fixture - the full test
# suite alone constructs 47+ in one process. Past ~16 uncapped instances
# the next `lb.Database()` fails with "Mmap for size 8796093022208
# failed" even though every individual test passes in isolation. 4GiB is
# far past this project's real ceiling (the DuckDB backend it replaces
# topped out at 42MB for a full site crawl).
_MAX_DB_SIZE_BYTES = 4 * 1024**3


class LadybugWriter:
    """Owns one `ladybug.Connection` on one dedicated thread.

    Every read and every write goes through `call()` - not just writes -
    for the same reason `DuckDBWriter` does: the single-connection
    constraint is about the connection, not the statement type.
    """

    def __init__(self, path: str) -> None:
        # Ladybug creates the database file itself but not missing parent
        # directories - same gap `DuckDBWriter.__init__` closes, for the
        # same reason (a fresh clone's gitignored data/sites/ won't exist
        # yet). "" (in-memory) has no directory component, so
        # os.path.dirname gives "" and there's nothing to create.
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # Cross-process guard, acquired before this thread ever opens
        # `lb.Database` - a second process opening the same `.lbdb` at the
        # same time is exactly what this exists to fail fast on, instead
        # of corrupting or hanging. Details: docs/dev/database/ladybug/writer.md#_lock
        self._lock = SiteLock(path)
        self._lock.acquire()

        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None
        self._thread = threading.Thread(
            target=self._run, args=(path,), daemon=True, name="ladybug-writer",
        )
        self._thread.start()
        self._ready.wait()
        if self._connect_error is not None:
            # Without this, a connect-time failure leaves the background
            # thread dead and _ready never set for any other reason,
            # hanging this wait() forever instead of surfacing the error.
            self._lock.release()
            raise self._connect_error

    def _run(self, path: str) -> None:
        try:
            database = lb.Database(path, max_db_size=_MAX_DB_SIZE_BYTES)
            conn = lb.Connection(database)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the constructor's thread
            self._connect_error = exc
            self._ready.set()
            return
        self._ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                # Both closed, not just the connection - `reset()`'s
                # close-unlink-reconnect needs the underlying file handle
                # fully released before the unlink, and Ladybug (unlike
                # DuckDB, whose connection alone owns the file) splits
                # that ownership across Connection and Database.
                conn.close()
                database.close()
                return
            future, fn = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(conn))
            except BaseException as exc:  # noqa: BLE001 - propagated to the caller, not swallowed
                future.set_exception(exc)

    def call(self, fn: Callable[[lb.Connection], Any]) -> Any:
        """Run `fn(connection)` on the writer thread and return its result.
        Blocks the calling thread - safe here because every call site
        already reaches this from inside `asyncio.to_thread` or a plain
        synchronous test, never from the event loop itself.
        """
        future: "Future[Any]" = Future()
        self._queue.put((future, fn))
        return future.result()

    def close(self) -> None:
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=10)
        # Released after the thread has (best-effort) shut the database
        # down - unconditionally, even if the thread was already dead,
        # so a lock this instance holds never outlives it.
        self._lock.release()

    def __del__(self) -> None:
        """Best-effort safety net, not the primary shutdown path - every
        real call site (`LadybugGraphStore.close()`, `Engine._run_async`)
        still closes explicitly and should keep doing so. Exists because
        this writer holds a real OS thread and an open embedded-database
        connection, unlike the pure-Python `InMemoryGraphStore` it
        replaces - a caller that forgets to close (confirmed live: most of
        this project's own test suite did, before this existed) leaks a
        thread that runs forever rather than one that quietly goes away
        with the object, and enough of those accumulating in one process
        exhausts a real resource ceiling.
        Details: docs/dev/database/ladybug/writer.md#__del__
        """
        try:
            self.close()
        except Exception:  # noqa: BLE001 - __del__ must never raise
            pass
