# database/ladybug/writer.py

## module

One dedicated thread owns the only `ladybug.Connection`; every caller submits a
closure to it and blocks for the result.

**The constraint.** Ladybug permits exactly one writer per database, and a
single connection is not safe to share across threads without serialization.
The crawl reaches storage from N async workers through `asyncio.to_thread`
(`graph_sink/sink.py::_write`) - real OS threads calling in at once. Callers
never touch the connection directly, so there is no second code path that could
reach it from another thread.

**Reads go through it too**, not just writes: the constraint is about the
connection, not the statement type. That also makes `_call` the single
choke point where every query in this package can be observed.

### `_MAX_DB_SIZE_BYTES`, and why it exists at all

Left at its default, a `Database` reserves ~8TB of virtual address space via
mmap - Ladybug's own docstring calls it a workaround "to get around... the
default 8TB mmap address space limit some environment [sic]... will be removed
once we implement a better solution later".

One instance is harmless. This project opens one store per site **plus one per
test fixture**, and the suite constructs 47+ in a single process. Past roughly
16 uncapped instances the next `lb.Database()` fails with `Mmap for size
8796093022208 failed`, while every individual test passes in isolation - the
worst shape a failure can have. Capped at 4GiB, which is far past this
project's real ceiling: the DuckDB backend it replaces topped out at 42MB for a
full site crawl.

### Connect-time failure

A failure inside the thread is stashed and re-raised in the **constructor's**
thread, and `_ready` is set on the failure path too. Without that, a
connect-time error would leave the background thread dead with `_ready` never
set for any other reason, so the constructor's `wait()` would hang forever
instead of surfacing the error.

### Missing parent directories

Ladybug creates the database itself but not the directories above it - the same
gap `DuckDBWriter` closed, for the same reason: a fresh clone's gitignored
`data/sites/` does not exist yet. The in-memory sentinel (`""`) has no directory
component, so there is nothing to create.

### Closing both, not just the connection

The shutdown path closes the `Connection` **and** the `Database`.
`LadybugGraphStore.reset()`'s close-unlink-reconnect needs the underlying file
handle fully released before the unlink, and Ladybug splits that ownership
across the two objects - unlike DuckDB, where the connection alone owns the
file. Closing only the connection leaves `reset()` unable to delete on Windows
and silently leaking a handle elsewhere.

## __del__

A best-effort safety net, **not** the shutdown path. Every real call site
(`LadybugGraphStore.close()`, `Engine._run_async`) still closes explicitly and
should keep doing so.

It exists because this writer holds a real OS thread and an open embedded
connection, unlike the pure-Python in-memory store it replaced. A caller that
forgets to close - which, confirmed live, most of this project's own test suite
did before this existed - leaks a thread that runs forever rather than one that
quietly goes away with the object, and enough of those in one process exhausts
a real resource ceiling. It swallows every exception, because `__del__` raising
during interpreter shutdown is worse than a leaked thread.
