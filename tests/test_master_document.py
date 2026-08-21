"""Unit tests for generators/master_document.py's llms.txt/manifest.json
addition (docs/adr/0015). master.md's own rendering (including the
accessibility-gap note) is tested in tests/test_document_pipeline.py."""
import json
from pathlib import Path

from core.documents import DocumentRequest, ProducedDocument
from generators.master_document import MasterDocument


def _document(name, kind, path, checksum="a" * 64, filename=None, purpose="p", title=None):
    """`relative_link` defaults to `path`'s own basename - what
    `generators/pipeline.py::_write_document` computes for every flat
    fixture path here (none of these tests exercise a nested document)."""
    return ProducedDocument(
        name=name, title=title or name.title(), purpose=purpose, path=path,
        kind=kind, checksum=checksum, filename=filename or name,
        relative_link=Path(path).name,
    )


def _request(produced):
    return DocumentRequest(graph_store=None, site="shop.example", agent=None, produced=tuple(produced))


def _outputs(produced):
    return MasterDocument().outputs(_request(produced))


# --- llms.txt sections (ADR-0015 point 1) ---

def test_a_source_document_lands_in_source_documents():
    produced = [_document("coverage", "source", "/out/x_coverage_1.json", filename="coverage")]

    llms = _outputs(produced)[1].content

    assert "## Source Documents" in llms
    assert "Coverage" in llms.split("## Source Documents")[1].split("##")[0]


def test_a_markdown_view_lands_in_views():
    produced = [_document("coverage", "view", "/out/x_coverage_1.md", filename="coverage")]

    llms = _outputs(produced)[1].content

    assert "## Views" in llms


def test_a_rule_catalog_lands_in_optional():
    produced = [_document("usability", "rule-catalog", "/out/x_usability-rules_1.json", filename="usability-rules")]

    llms = _outputs(produced)[1].content

    assert "## Optional" in llms


def test_a_tooling_projection_lands_in_optional():
    produced = [_document("architecture", "projection", "/out/x_architecture.cyclonedx_1.json", filename="architecture.cyclonedx")]

    llms = _outputs(produced)[1].content

    assert "## Optional" in llms


def test_links_within_a_section_follow_the_resolution_order():
    produced = [
        _document("flows", "source", "/out/x_flows.xstate_1.json", filename="flows.xstate"),
        _document("coverage", "source", "/out/x_coverage_1.json", filename="coverage"),
        _document("tree", "source", "/out/x_tree.aria_1.yaml", filename="tree.aria"),
    ]

    llms = _outputs(produced)[1].content

    section = llms.split("## Source Documents")[1].split("##")[0]
    assert section.index("Coverage") < section.index("Tree") < section.index("Flows")


def test_an_unlisted_name_sorts_after_every_named_one():
    """A future document not yet in ADR-0015's own list must not error -
    it sorts last, alphabetically among any other unlisted names."""
    produced = [
        _document("coverage", "source", "/out/x_coverage_1.json", filename="coverage"),
        _document("zzz-future", "source", "/out/x_zzz-future_1.json", filename="zzz-future"),
    ]

    llms = _outputs(produced)[1].content

    section = llms.split("## Source Documents")[1].split("##")[0]
    assert section.index("Coverage") < section.index("Zzz-Future")


def test_an_empty_section_is_omitted_entirely():
    produced = [_document("coverage", "source", "/out/x_coverage_1.json", filename="coverage")]

    llms = _outputs(produced)[1].content

    assert "## Optional" not in llms


# --- manifest.json (ADR-0015 point 2) ---

def test_an_on_entry_carries_real_path_kind_and_checksum():
    produced = [_document("coverage", "source", "/out/x_coverage_1.json", checksum="f" * 64, filename="coverage")]

    manifest = json.loads(_outputs(produced)[2].content)

    entry = next(e for e in manifest["documents"] if e["name"] == "coverage" and e["kind"] == "source")
    assert entry["status"] == "on"
    assert entry["path"] == "x_coverage_1.json"
    assert entry["checksum"] == f"sha256:{'f' * 64}"


def test_a_known_format_is_cited_from_the_lookup_table():
    produced = [_document("coverage", "source", "/out/x_coverage_1.json", filename="coverage")]

    manifest = json.loads(_outputs(produced)[2].content)

    entry = next(e for e in manifest["documents"] if e["name"] == "coverage" and e["kind"] == "source")
    assert entry["format"] == "JSON Schema 2020-12"


def test_a_view_gets_markdown_format_even_when_its_source_sibling_has_a_different_one():
    """coverage.json and coverage.md share one `filename` stem - the
    source's external-standard format must not leak onto the view."""
    produced = [
        _document("coverage", "source", "/out/x_coverage_1.json", filename="coverage"),
        _document("coverage", "view", "/out/x_coverage_1.md", filename="coverage"),
    ]

    manifest = json.loads(_outputs(produced)[2].content)

    view_entry = next(e for e in manifest["documents"] if e["kind"] == "view")
    assert view_entry["format"] == "Markdown"


def test_an_unknown_filename_gets_no_format_rather_than_a_guess():
    produced = [_document("mystery", "source", "/out/x_mystery_1.json", filename="mystery")]

    manifest = json.loads(_outputs(produced)[2].content)

    entry = next(e for e in manifest["documents"] if e["name"] == "mystery")
    assert "format" not in entry


def test_a_registered_but_unproduced_document_appears_as_off():
    """status is never a second, hand-maintained flag - it mirrors
    request.produced, so a real off-by-config document appears with no
    path/kind/checksum to describe (no file exists)."""
    manifest = json.loads(_outputs([])[2].content)

    entry = next(e for e in manifest["documents"] if e["name"] == "coverage")
    assert entry["status"] == "off"
    assert "path" not in entry and "checksum" not in entry


def test_master_itself_never_appears_in_its_own_manifest():
    manifest = json.loads(_outputs([])[2].content)

    assert all(entry["name"] != "master" for entry in manifest["documents"])


def test_manifest_validates_against_its_own_schema():
    """generate() already calls validate_against_schema internally -
    reaching this point at all (no exception) is the real assertion."""
    produced = [
        _document("coverage", "source", "/out/x_coverage_1.json", filename="coverage"),
        _document("coverage", "view", "/out/x_coverage_1.md", filename="coverage"),
        _document("usability", "rule-catalog", "/out/x_usability-rules_1.json", filename="usability-rules"),
    ]

    manifest = json.loads(_outputs(produced)[2].content)

    assert manifest["documents"]
