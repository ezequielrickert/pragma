"""Regression tests for `database/ladybug/site_lock.py::SiteLock` - the
cross-process advisory lock guarding one site's `.lbdb`, in isolation
from `LadybugWriter`/`LadybugGraphStore` (see tests/test_ladybug_store.py
for the integration-level proof that a second `connect()` is actually
blocked).
"""
import os

import pytest

from database.ladybug.site_lock import SiteLock, SiteLockError


def test_acquire_then_release_lets_a_second_lock_acquire_afterward(tmp_path):
    db_path = str(tmp_path / "shop.example.lbdb")

    first = SiteLock(db_path)
    first.acquire()
    first.release()

    second = SiteLock(db_path)
    second.acquire()  # must not raise - the first lock already let go
    second.release()


def test_a_second_lock_on_the_same_path_fails_fast(tmp_path):
    db_path = str(tmp_path / "shop.example.lbdb")

    first = SiteLock(db_path)
    first.acquire()
    try:
        second = SiteLock(db_path)
        with pytest.raises(SiteLockError, match="already locked"):
            second.acquire()
    finally:
        first.release()


def test_locks_on_different_paths_never_contend(tmp_path):
    a = SiteLock(str(tmp_path / "a.example.lbdb"))
    b = SiteLock(str(tmp_path / "b.example.lbdb"))
    a.acquire()
    b.acquire()  # different site, must not raise
    a.release()
    b.release()


def test_empty_path_is_a_no_op_lock():
    """`""` is Ladybug's own in-memory sentinel - nothing on disk to
    protect, so two "locks" on it never contend."""
    a = SiteLock("")
    b = SiteLock("")
    a.acquire()
    b.acquire()  # must not raise
    a.release()
    b.release()


def test_release_before_acquire_is_a_safe_no_op(tmp_path):
    lock = SiteLock(str(tmp_path / "shop.example.lbdb"))
    lock.release()  # must not raise


def test_release_is_idempotent(tmp_path):
    lock = SiteLock(str(tmp_path / "shop.example.lbdb"))
    lock.acquire()
    lock.release()
    lock.release()  # must not raise a second time


def test_lock_file_lives_alongside_the_db_path_not_inside_it(tmp_path):
    db_path = str(tmp_path / "shop.example.lbdb")
    lock = SiteLock(db_path)
    lock.acquire()
    try:
        assert os.path.exists(db_path + ".lock")
        assert not os.path.isdir(db_path)  # never created the db directory itself
    finally:
        lock.release()
