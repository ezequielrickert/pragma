"""Cross-process advisory lock guarding one site's `.lbdb`.

`LadybugWriter`'s single dedicated thread already serializes every
read/write *within* one process - the actual constraint Ladybug/Kùzu
itself enforces (one writer per database) was never at risk there. What
it never guarded against is a *second process* opening the same site's
database at the same time - two stage invocations against the same
site (`pragma static` and `pragma dynamic` launched concurrently by
mistake, say) racing to open the same `.lbdb` directory. This module is
that second, cross-process guard: an OS-level advisory lock on a small
sentinel file placed *alongside* the `.lbdb` directory, not inside it -
Ladybug owns everything under the directory itself, and this needs to
survive independently of whatever Ladybug does or doesn't clean up
there.

Details: docs/dev/database/ladybug/site_lock.md#module
"""
from __future__ import annotations

import os
from typing import Optional

try:
    import fcntl
    _FLOCK_AVAILABLE = True
except ImportError:  # pragma: no cover - this project targets macOS/Linux
    fcntl = None  # type: ignore[assignment]
    _FLOCK_AVAILABLE = False


class SiteLockError(RuntimeError):
    """Raised when another process already holds a site's lock.
    Details: docs/dev/database/ladybug/site_lock.md#sitelockerror
    """


class SiteLock:
    """One advisory, exclusive, cross-process lock for one site's `.lbdb`.
    Details: docs/dev/database/ladybug/site_lock.md#sitelock
    """

    def __init__(self, db_path: str) -> None:
        # "" is Ladybug's own in-memory sentinel (LadybugGraphStore's
        # "memory" backend, `directory=None`) - nothing on disk to
        # protect, so this lock is a no-op for it throughout.
        self._lock_path = f"{db_path}.lock" if db_path else ""
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        """Fails fast (`SiteLockError`) if another process already holds
        this site's lock, rather than letting two writers corrupt or
        hang against the same `.lbdb`.
        Details: docs/dev/database/ladybug/site_lock.md#acquire
        """
        if not self._lock_path or not _FLOCK_AVAILABLE:
            return
        directory = os.path.dirname(self._lock_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise SiteLockError(
                f"{self._lock_path} is already locked by another pragma process - "
                "wait for it to finish, or make sure two commands aren't running "
                "against the same site at once."
            ) from exc
        self._fd = fd

    def release(self) -> None:
        """Safe to call even if `acquire()` never ran or was a no-op.
        Details: docs/dev/database/ladybug/site_lock.md#release
        """
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None
