# `database/ladybug/site_lock.py`

## module

Cross-process advisory lock guarding one site's `.lbdb`. `LadybugWriter`'s
single dedicated thread already serializes every read/write *within* one
process - the actual constraint Ladybug/Kùzu itself enforces (one writer
per database) was never at risk there. What it never guarded against is a
*second process* opening the same site's database at the same time - two
stage invocations against the same site (`pragma static` and `pragma
dynamic` launched concurrently by mistake, say) racing to open the same
`.lbdb` directory. This module is that second, cross-process guard: an
OS-level advisory lock on a small sentinel file placed *alongside* the
`.lbdb` directory, not inside it - Ladybug owns everything under the
directory itself, and this needs to survive independently of whatever
Ladybug does or doesn't clean up there.

`fcntl`-based (POSIX `flock`) - this project targets macOS/Linux; on a
platform without `fcntl` the lock degrades to a silent no-op rather than
an import-time crash, since a missing cross-process guard is a narrower
failure than the tool not running at all.

## sitelockerror

Raised by `acquire()` when another process already holds the lock -
propagates all the way up to whichever `pragma` command tried to connect,
per `core/engine.py`'s own `from_config` (and `StaticEngine`/
`DynamicEngine`'s matching guards): every one of them special-cases this
error to *not* fall back to an in-memory store the way a genuine backend
failure would, since silently crawling into a throwaway store would
defeat the entire point of failing fast here.

## sitelock

One advisory, exclusive, cross-process lock for one site's `.lbdb`. `""`
(Ladybug's own in-memory sentinel - the `"memory"` graph-store backend,
`directory=None`) makes every method a no-op: nothing on disk to protect,
so two "locks" on it never contend.

## acquire

`os.open(..., O_CREAT | O_RDWR)` then a non-blocking `flock(LOCK_EX |
LOCK_NB)` - fails immediately (`SiteLockError`) rather than blocking, so
a second process finds out right away instead of hanging until the first
one finishes. Creates the lock file's parent directory first, same gap
`LadybugWriter.__init__` already closes for the `.lbdb` path itself (a
fresh clone's gitignored `data/sites/` won't exist yet).

## release

Safe to call even if `acquire()` never ran (empty path, `fcntl`
unavailable) or already released - `LadybugWriter.close()` calls this
unconditionally, whether or not its own writer thread was still alive.
