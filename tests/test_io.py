"""Tests for utils/io.py's run-manifest helpers
(docs/explicativos/plan-almacenamiento.md Fase A) - record_run_manifest is
the append-only index Engine writes to on every run, get_latest_run is its
read-side counterpart.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from utils.io import generate_docs_index, get_latest_run, record_run_manifest


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


def test_generate_docs_index_with_no_manifest_yet(out_dir):
    doc = generate_docs_index(out_dir)
    assert "No runs recorded yet" in doc


def test_generate_docs_index_lists_most_recent_run_first(out_dir):
    record_run_manifest(
        out_dir, "example.com",
        {
            "timestamp": "20260101T000000Z", "pages_finished": 3, "pages_total": 3,
            "components_total": 10, "components_unexplored": 0,
            "prd_path": f"{out_dir}/example.com_prd_20260101T000000Z.md",
            "tree_path": f"{out_dir}/example.com_tree_20260101T000000Z.md",
            "export_path": None,
        },
    )
    record_run_manifest(
        out_dir, "example.com",
        {
            "timestamp": "20260102T000000Z", "pages_finished": 5, "pages_total": 5,
            "components_total": 20, "components_unexplored": 1,
            "prd_path": f"{out_dir}/example.com_prd_20260102T000000Z.md",
            "tree_path": f"{out_dir}/example.com_tree_20260102T000000Z.md",
            "export_path": f"{out_dir}/example.com_graph_20260102T000000Z.json",
        },
    )

    doc = generate_docs_index(out_dir)
    assert "## example.com" in doc
    first_row_idx = doc.index("20260102T000000Z")
    second_row_idx = doc.index("20260101T000000Z")
    assert first_row_idx < second_row_idx, "most recent run must be listed first"
    assert "[PRD](example.com_prd_20260102T000000Z.md)" in doc
    assert "[JSON](example.com_graph_20260102T000000Z.json)" in doc
    assert "5/5" in doc


def test_generate_docs_index_handles_missing_export_path(out_dir):
    record_run_manifest(
        out_dir, "example.com",
        {
            "timestamp": "1", "pages_finished": 1, "pages_total": 1,
            "components_total": 1, "components_unexplored": 0,
            "prd_path": "x_prd.md", "tree_path": "x_tree.md", "export_path": None,
        },
    )
    doc = generate_docs_index(out_dir)
    # A "-" placeholder, not a broken/empty Markdown link, when export_json was off.
    assert "| - |" in doc


def test_generate_docs_index_lists_multiple_sites_separately(out_dir):
    record_run_manifest(out_dir, "a.com", {"timestamp": "1", "prd_path": "a.md"})
    record_run_manifest(out_dir, "b.com", {"timestamp": "1", "prd_path": "b.md"})
    doc = generate_docs_index(out_dir)
    assert "## a.com" in doc
    assert "## b.com" in doc
    assert doc.index("## a.com") < doc.index("## b.com"), "sites listed alphabetically"


def test_generate_docs_index_survives_a_corrupted_manifest(out_dir):
    manifest_path = Path(out_dir) / "runs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not valid json", encoding="utf-8")

    doc = generate_docs_index(out_dir)  # must not raise
    assert "could not be read" in doc
