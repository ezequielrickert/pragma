"""Unit tests for interactive/customization.py - ADR-0031's "effective
document" lookup and customized-document writer (ticket #151)."""
from pathlib import Path

import jsonschema
import pytest
import yaml

from interactive.customization import (
    SCHEMA_PATH_BY_FILENAME,
    DocumentRef,
    SiteOutput,
    available_documents,
    customized_path,
    effective_content,
    save_customized,
    schema_path_for,
)

SITE = "example.com"


def _where(out_dir) -> SiteOutput:
    return SiteOutput(out_dir=str(out_dir), site=SITE)


def _write_original(tmp_path, filename, extension, timestamp, content="{}"):
    (tmp_path / f"example.com_{filename}_{timestamp}.{extension}").write_text(content, encoding="utf-8")


def test_available_documents_finds_every_distinct_file_newest_run_only(tmp_path):
    _write_original(tmp_path, "tokens", "json", "20260101T000000Z")
    _write_original(tmp_path, "tokens", "md", "20260101T000000Z")
    _write_original(tmp_path, "coverage", "json", "20260101T000000Z")
    # A different site's file must never leak in.
    (tmp_path / "other.example_tokens_20260101T000000Z.json").write_text("{}", encoding="utf-8")

    refs = available_documents(_where(tmp_path))

    assert refs == [
        DocumentRef(filename="coverage", extension="json"),
        DocumentRef(filename="tokens", extension="json"),
        DocumentRef(filename="tokens", extension="md"),
    ]


def test_effective_content_falls_back_to_the_original_when_never_customized(tmp_path):
    _write_original(tmp_path, "tokens", "json", "20260101T000000Z", content='{"core": {}}')

    content = effective_content(_where(tmp_path), DocumentRef("tokens", "json"))

    assert content == '{"core": {}}'


def test_effective_content_picks_the_most_recent_original_when_several_runs_exist(tmp_path):
    _write_original(tmp_path, "tokens", "json", "20260101T000000Z", content='{"run": "first"}')
    _write_original(tmp_path, "tokens", "json", "20260215T120000Z", content='{"run": "second"}')

    content = effective_content(_where(tmp_path), DocumentRef("tokens", "json"))

    assert content == '{"run": "second"}'


def test_effective_content_prefers_the_customized_copy_over_the_original(tmp_path):
    """ADR-0031's own read-time-resolution rule - the whole point of
    this module. Uses gherkin (no known schema) to test the write path
    on its own, independent of any real schema's required fields."""
    where = _where(tmp_path)
    ref = DocumentRef("gherkin", "feature")
    _write_original(tmp_path, "gherkin", "feature", "20260101T000000Z", content="Feature: original\n")
    save_customized(where, ref, "Feature: edited\n")

    content = effective_content(where, ref)

    assert content == "Feature: edited\n"


def test_effective_content_is_none_when_neither_exists(tmp_path):
    assert effective_content(_where(tmp_path), DocumentRef("tokens", "json")) is None


def test_customized_path_is_flat_and_stable_across_edits():
    """Not one file per edit, not a per-site subdirectory - ADR-0031's
    own corrected path convention."""
    path = customized_path(SiteOutput(out_dir="data/output", site=SITE), DocumentRef("tokens", "json"))

    assert path == "data/output/customized/example.com_tokens.json"


def test_save_customized_writes_to_the_stable_customized_path(tmp_path):
    save_customized(_where(tmp_path), DocumentRef("gherkin", "feature"), "Feature: x\n")

    written = (tmp_path / "customized" / "example.com_gherkin.feature").read_text(encoding="utf-8")
    assert written == "Feature: x\n"


def test_save_customized_overwrites_in_place_not_accumulating_files(tmp_path):
    where = _where(tmp_path)
    ref = DocumentRef("gherkin", "feature")
    save_customized(where, ref, "Feature: first\n")
    save_customized(where, ref, "Feature: second\n")

    customized_dir = tmp_path / "customized"
    assert [p.name for p in customized_dir.iterdir()] == ["example.com_gherkin.feature"]
    assert (customized_dir / "example.com_gherkin.feature").read_text() == "Feature: second\n"


def test_save_customized_rejects_content_that_breaks_the_real_schema(tmp_path):
    """coverage.schema.json is a real, vendored schema - {} is missing
    every required field."""
    with pytest.raises(jsonschema.ValidationError):
        save_customized(_where(tmp_path), DocumentRef("coverage", "json"), "{}")


def test_save_customized_validates_yaml_documents_by_parsing_first(tmp_path):
    """tree.aria.yaml is schema-validated but is YAML, not JSON -
    _parse_for_validation has to know the difference."""
    invalid_yaml = yaml.safe_dump({"not": "a valid tree.aria shape"})

    with pytest.raises(jsonschema.ValidationError):
        save_customized(_where(tmp_path), DocumentRef("tree.aria", "yaml"), invalid_yaml)


def test_save_customized_skips_validation_for_a_document_with_no_known_schema(tmp_path):
    """gherkin's .feature carries no schema at all - a save must still
    succeed, not silently require one that doesn't exist."""
    save_customized(_where(tmp_path), DocumentRef("gherkin", "feature"), "Feature: whatever\n")

    assert schema_path_for("gherkin") is None
    written = (tmp_path / "customized" / "example.com_gherkin.feature").read_text(encoding="utf-8")
    assert written == "Feature: whatever\n"


def test_every_schema_path_in_the_table_points_at_a_real_file():
    """A typo here would silently disable validation for that one
    document - the table's own integrity, checked directly."""
    missing = [path for path in SCHEMA_PATH_BY_FILENAME.values() if not Path(path).exists()]

    assert missing == []
