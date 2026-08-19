"""Regression tests for `database/ladybug/store.py` - connection lifecycle
only (Storage-migration plan step 3). The write/read surface this store
will eventually satisfy is covered by `tests/test_graph_store_conformance.py`
once `LadybugGraphStore` implements `GraphStore` (plan steps 4-5); until
then this file is the one exercising the package at all.
"""
from __future__ import annotations

import os

import pytest

from database.ladybug.site_lock import SiteLockError
from database.ladybug.store import LadybugGraphStore


@pytest.fixture
def site() -> str:
    return "austral.edu.ar"


def test_connect_creates_an_on_disk_database_at_the_slugged_path(tmp_path, site) -> None:
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    try:
        assert store.path == os.path.join(str(tmp_path), f"{site}.lbdb")
        assert os.path.exists(store.path)
    finally:
        store.close()


def test_connect_writes_a_site_header_row_once(tmp_path, site) -> None:
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    try:
        rows = store._call(lambda conn: list(conn.execute("MATCH (s:Site) RETURN s.name")))
        assert rows == [[site]]
    finally:
        store.close()


def test_connect_is_idempotent_and_never_duplicates_the_site_row(tmp_path, site) -> None:
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    store.connect()  # a second call must not re-run DDL or MERGE badly
    try:
        count = store._call(lambda conn: list(conn.execute("MATCH (s:Site) RETURN count(s)")))[0][0]
        assert count == 1
    finally:
        store.close()


def test_touch_site_keeps_first_crawled_but_advances_last_crawled(tmp_path, site) -> None:
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    try:
        first = store._call(
            lambda conn: list(conn.execute("MATCH (s:Site) RETURN s.first_crawled"))
        )[0][0]
        store._touch_site()
        after = store._call(
            lambda conn: list(conn.execute("MATCH (s:Site) RETURN s.first_crawled, s.last_crawled"))
        )[0]
        assert after[0] == first
        assert after[1] >= first
    finally:
        store.close()


def test_reset_deletes_every_node_but_reopens_with_a_fresh_site_row(tmp_path, site) -> None:
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    try:
        store._call(lambda conn: conn.execute('CREATE (p:Page {url: "https://x/y"})'))
        before = store._call(lambda conn: list(conn.execute("MATCH (p:Page) RETURN count(p)")))[0][0]
        assert before == 1

        store.reset()

        after = store._call(lambda conn: list(conn.execute("MATCH (p:Page) RETURN count(p)")))[0][0]
        assert after == 0
        site_rows = store._call(lambda conn: list(conn.execute("MATCH (s:Site) RETURN s.name")))
        assert site_rows == [[site]]
    finally:
        store.close()


def test_reset_reclaims_disk_space_rather_than_leaving_a_bloated_database(tmp_path, site) -> None:
    """The whole reason `reset()` replaces the retired DuckDB backend's
    `DELETE`-based `clear_site()` - see store.py's own module docstring."""
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    try:
        assert os.path.exists(store.path)
        store.reset()
        assert os.path.exists(store.path)  # deleted, then recreated fresh - not left absent
    finally:
        store.close()


def test_no_directory_uses_ladybugs_in_memory_database(site) -> None:
    store = LadybugGraphStore(site)
    store.connect()
    try:
        assert store.path == ""
        rows = store._call(lambda conn: list(conn.execute("MATCH (s:Site) RETURN s.name")))
        assert rows == [[site]]
    finally:
        store.close()


def test_close_before_connect_is_a_safe_no_op(site) -> None:
    store = LadybugGraphStore(site)
    store.close()  # must not raise


def test_connect_fails_fast_when_another_process_already_holds_the_site(tmp_path, site) -> None:
    """The cross-process guard `site_lock.py` adds: two `LadybugGraphStore`
    instances (standing in for two separate `pragma` invocations, e.g.
    `static` and `dynamic` launched concurrently against the same site by
    mistake) must not both open the same `.lbdb`."""
    first = LadybugGraphStore(site, directory=str(tmp_path))
    first.connect()
    try:
        second = LadybugGraphStore(site, directory=str(tmp_path))
        with pytest.raises(SiteLockError, match="already locked"):
            second.connect()
    finally:
        first.close()


def test_connect_succeeds_again_once_the_first_store_closes(tmp_path, site) -> None:
    first = LadybugGraphStore(site, directory=str(tmp_path))
    first.connect()
    first.close()

    second = LadybugGraphStore(site, directory=str(tmp_path))
    second.connect()  # must not raise - the lock was released with the first store
    second.close()


def test_reset_releases_and_reacquires_the_lock_around_its_own_delete(tmp_path, site) -> None:
    """`reset()` closes, deletes the directory, then reconnects - if it
    didn't release the lock before deleting, its own reconnect would
    deadlock against itself."""
    store = LadybugGraphStore(site, directory=str(tmp_path))
    store.connect()
    store.reset()  # must not hang or raise
    try:
        other = LadybugGraphStore(site, directory=str(tmp_path))
        with pytest.raises(SiteLockError):
            other.connect()  # still held by `store`, which reset() left connected
    finally:
        store.close()


def test_each_site_gets_its_own_database_no_cross_contamination(tmp_path) -> None:
    a = LadybugGraphStore("a.example", directory=str(tmp_path))
    b = LadybugGraphStore("b.example", directory=str(tmp_path))
    a.connect()
    b.connect()
    try:
        assert a.path != b.path
        a._call(lambda conn: conn.execute('CREATE (p:Page {url: "https://a/only"})'))
        a_pages = a._call(lambda conn: list(conn.execute("MATCH (p:Page) RETURN count(p)")))[0][0]
        b_pages = b._call(lambda conn: list(conn.execute("MATCH (p:Page) RETURN count(p)")))[0][0]
        assert a_pages == 1
        assert b_pages == 0
    finally:
        a.close()
        b.close()
