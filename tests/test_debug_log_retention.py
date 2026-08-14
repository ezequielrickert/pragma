"""Tests for spiders/debug_log.py::prune_old_runs
(docs/explicativos/plan-almacenamiento.md Fase A) - opt-in retention for
debug_logs/ run directories."""
import os
import shutil
import tempfile

import pytest

from spiders.debug_log import prune_old_runs


@pytest.fixture
def debug_logs_dir():
    d = tempfile.mkdtemp()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _make_run_dir(debug_logs_dir: str, name: str) -> str:
    path = os.path.join(debug_logs_dir, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "debug.md"), "w", encoding="utf-8") as f:
        f.write("placeholder")
    return path


def test_none_keep_last_is_a_noop(debug_logs_dir):
    _make_run_dir(debug_logs_dir, "example.com_1")
    _make_run_dir(debug_logs_dir, "example.com_2")

    removed = prune_old_runs(debug_logs_dir, "example.com", keep_last=None)

    assert removed == []
    assert len(os.listdir(debug_logs_dir)) == 2


def test_keeps_only_the_n_most_recent_by_name_order(debug_logs_dir):
    for ts in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        _make_run_dir(debug_logs_dir, f"example.com_{ts}")

    removed = prune_old_runs(debug_logs_dir, "example.com", keep_last=1)

    remaining = sorted(os.listdir(debug_logs_dir))
    assert remaining == ["example.com_20260103T000000Z"]
    assert len(removed) == 2


def test_never_deletes_below_keep_last(debug_logs_dir):
    _make_run_dir(debug_logs_dir, "example.com_1")

    removed = prune_old_runs(debug_logs_dir, "example.com", keep_last=5)

    assert removed == []
    assert len(os.listdir(debug_logs_dir)) == 1


def test_scoped_to_slug_never_touches_other_sites(debug_logs_dir):
    _make_run_dir(debug_logs_dir, "example.com_1")
    _make_run_dir(debug_logs_dir, "example.com_2")
    _make_run_dir(debug_logs_dir, "other.com_1")

    prune_old_runs(debug_logs_dir, "example.com", keep_last=1)

    remaining = sorted(os.listdir(debug_logs_dir))
    assert remaining == ["example.com_2", "other.com_1"]


def test_missing_debug_logs_dir_is_a_noop():
    removed = prune_old_runs("/nonexistent/path/really", "example.com", keep_last=1)
    assert removed == []
