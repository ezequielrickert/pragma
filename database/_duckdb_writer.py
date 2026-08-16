"""Single-writer-thread serialization for `DuckDBGraphStore` and its mixins.

DuckDB permits exactly one writer *process*, and within a process a single
connection isn't safe to share across threads without serialization -
concurrent same-row `UPDATE`s raise a conflict error, and the crawl reaches
storage from N async workers via `asyncio.to_thread`
(`spiders/orchestration/graph_sink/sink.py::_write`), i.e. real OS threads
calling in at once. `_DuckDBWriter` is the fix: one dedicated thread owns
the only connection, every caller's SQL runs as a closure submitted to it
and blocks for the result - callers never touch `duckdb.DuckDBPyConnection`
directly, so there is no second code path that could reach the connection
from another thread.

Details: docs/dev/database/_duckdb_writer.md#module
"""
from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable

import duckdb


class DuckDBWriter:
    """Owns one `duckdb.DuckDBPyConnection` on one dedicated thread.

    Every read and every write goes through `call()` - not just writes -
    because DuckDB's single-writer constraint is about the *connection*,
    not specifically about statement type; a reader on a different thread
    racing a writer on this one is the same class of bug the plan this
    backend implements (`storage-plan.md`'s Phase 3) exists to rule out by
    construction rather than by discipline.
    """

    def __init__(self, path: str) -> None:
        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(path,), daemon=True, name="duckdb-writer",
        )
        self._thread.start()
        self._ready.wait()

    def _run(self, path: str) -> None:
        conn = duckdb.connect(path)
        self._ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                conn.close()
                return
            future, fn = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(conn))
            except BaseException as exc:  # noqa: BLE001 - propagated to the caller, not swallowed
                future.set_exception(exc)

    def call(self, fn: Callable[[duckdb.DuckDBPyConnection], Any]) -> Any:
        """Run `fn(connection)` on the writer thread and return its result.
        Blocks the calling thread - safe here because every call site
        already reaches this from inside `asyncio.to_thread` or a plain
        synchronous test, never from the event loop itself.
        """
        future: "Future[Any]" = Future()
        self._queue.put((future, fn))
        return future.result()

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        self._queue.put(None)
        self._thread.join(timeout=10)
