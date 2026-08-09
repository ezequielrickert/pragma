"""Tests for src/utils/io.py's run-manifest helpers
(docs/explicativos/plan-almacenamiento.md Fase A) - record_run_manifest is
the append-only index Engine writes to on every run, get_latest_run is its
read-side counterpart.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from src.utils.io import get_latest_run, record_run_manifest


@pytest.fixture
def out_dir():
    d = tempfile.mkdtemp()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_run_manifest_creates_file_and_appends(out_dir):
    path1 = record_run_manifest(out_dir, "example.com", {"timestamp": "1", "prd_path": "a.md"})
    path2 = record_run_manifest(out_dir, "example.com", {"timestamp": "2", "prd_path": "b.md"})

    assert path1 == path2 == str(Path(out_dir) / "runs.json")
    data = json.loads(Path(path1).read_text(encoding="utf-8"))
    assert [e["timestamp"] for e in data["example.com"]] == ["1", "2"]


def test_record_run_manifest_keeps_sites_separate(out_dir):
    record_run_manifest(out_dir, "a.com", {"timestamp": "1"})
    record_run_manifest(out_dir, "b.com", {"timestamp": "1"})

    data = json.loads((Path(out_dir) / "runs.json").read_text(encoding="utf-8"))
    assert set(data.keys()) == {"a.com", "b.com"}
    assert len(data["a.com"]) == 1
    assert len(data["b.com"]) == 1


def test_record_run_manifest_survives_a_corrupted_existing_file(out_dir):
    manifest_path = Path(out_dir) / "runs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not valid json", encoding="utf-8")

    # Must not raise - a broken manifest is documentation enrichment, not
    # something a real crawl's completion should ever depend on.
    record_run_manifest(out_dir, "example.com", {"timestamp": "1"})

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["example.com"][0]["timestamp"] == "1"


def test_get_latest_run_returns_last_entry(out_dir):
    record_run_manifest(out_dir, "example.com", {"timestamp": "1"})
    record_run_manifest(out_dir, "example.com", {"timestamp": "2"})

    assert get_latest_run(out_dir, "example.com") == {"timestamp": "2"}


def test_get_latest_run_empty_when_no_manifest_or_no_entry(out_dir):
    assert get_latest_run(out_dir, "never-crawled.com") == {}

    record_run_manifest(out_dir, "example.com", {"timestamp": "1"})
    assert get_latest_run(out_dir, "other-site.com") == {}
