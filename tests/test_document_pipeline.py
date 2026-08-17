"""Unit tests for the document pipeline (generators/pipeline.py,
coverage.py, master_document.py) - built against LadybugGraphStore in-memory
mode and a stub agent, no crawl or browser needed."""
from pathlib import Path

import pytest

from core import bootstrap  # noqa: F401  (registers the document generators)
from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from generators.coverage import build_coverage, render_coverage_banner
from generators.pipeline import DocumentNaming, run_document_pipeline
from database.ladybug.store import LadybugGraphStore

SITE = "pipeline-test-site"
TIMESTAMP = "20260812T120000Z"


class StubAgent:
    """`generate()` returns a marker, so a document that reached the model
    is distinguishable from one that only read the graph."""

    def generate(self, prompt, system_instruction=None):
        return "STUB NARRATION"


def _naming(tmp_path):
    return DocumentNaming(out_dir=str(tmp_path), slug="example.com", timestamp=TIMESTAMP)


def _request(tmp_path_store=None):
    store = tmp_path_store or LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("example.com/", status="Finished", components=1, title="Home")
    store.upsert_page("example.com/cart", status="Pending", components=0)
    store.record_component("example.com/", "div > button", tag="button", text="Buy")
    return DocumentRequest(graph_store=store, site=SITE, agent=StubAgent())


def test_naming_builds_the_path_from_the_registry_name():
    naming = DocumentNaming(out_dir="out", slug="example.com", timestamp=TIMESTAMP)

    assert naming.path_for("prd", "md") == f"out/example.com_prd_{TIMESTAMP}.md"


def test_build_coverage_counts_finished_pages_only():
    coverage = build_coverage(_request().graph_store)

    assert coverage.pages_finished == 1
    assert coverage.pages_total == 2
    assert coverage.pages_percent == 50
    assert coverage.unfinished_urls == ["example.com/cart"]


def test_build_coverage_reports_zero_percent_for_an_empty_site():
    """A site with nothing recorded is a real outcome, not a ZeroDivisionError."""
    store = LadybugGraphStore("never-crawled.example")
    store.connect()

    coverage = build_coverage(store)

    assert coverage.pages_percent == 0
    assert coverage.components_percent == 0


def test_coverage_banner_states_the_public_surface_scope():
    """The scope caveat is the whole point of the banner - a document that
    silently omits everything behind a login is worse than one that says so."""
    banner = render_coverage_banner(build_coverage(_request().graph_store))

    assert "does not sign in" in banner
    assert "1/2 pages" in banner


def test_pipeline_writes_each_requested_document_plus_the_master(tmp_path):
    produced = run_document_pipeline(_request(), _naming(tmp_path), ["coverage", "tree"])

    assert [document.name for document in produced] == ["coverage", "tree", "master"]
    for document in produced:
        assert Path(document.path).exists()


def test_master_document_links_every_document_that_was_written(tmp_path):
    produced = run_document_pipeline(_request(), _naming(tmp_path), ["coverage", "tree"])

    master_text = Path(produced[-1].path).read_text(encoding="utf-8")

    assert f"(example.com_coverage_{TIMESTAMP}.md)" in master_text
    assert f"(example.com_tree_{TIMESTAMP}.md)" in master_text


def test_markdown_documents_carry_the_coverage_banner(tmp_path):
    produced = run_document_pipeline(_request(), _naming(tmp_path), ["tree"])

    tree_text = Path(produced[0].path).read_text(encoding="utf-8")

    assert tree_text.startswith("> **Crawl coverage:**")


def test_json_documents_do_not_carry_the_banner(tmp_path):
    """A JSON file with a Markdown blockquote glued to the front is not JSON."""
    produced = run_document_pipeline(_request(), _naming(tmp_path), ["export"])

    assert Path(produced[0].path).read_text(encoding="utf-8").lstrip().startswith("{")


def test_a_failing_generator_is_skipped_without_losing_the_others(tmp_path, capsys):
    @DOCUMENT_REGISTRY.register("exploding")
    class ExplodingDocument(DocumentGenerator):
        name = "exploding"
        title = "Exploding"
        purpose = "Fails on purpose."

        def generate(self, request):
            raise RuntimeError("boom")

    produced = run_document_pipeline(_request(), _naming(tmp_path), ["exploding", "coverage"])

    assert [document.name for document in produced] == ["coverage", "master"]
    assert "boom" in capsys.readouterr().out
    # The master document must never link to a file that was never written.
    master_text = Path(produced[-1].path).read_text(encoding="utf-8")
    assert "exploding" not in master_text


def test_unknown_document_name_is_reported_and_skipped(tmp_path, capsys):
    produced = run_document_pipeline(_request(), _naming(tmp_path), ["not-a-document", "coverage"])

    assert [document.name for document in produced] == ["coverage", "master"]
    assert "not-a-document" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["coverage", "prd", "tree", "export"])
def test_every_registered_document_declares_its_identity(name):
    """`name`/`title`/`purpose` are what the master document renders - a
    generator that leaves them blank produces an unusable index entry."""
    generator = DOCUMENT_REGISTRY.create(name)

    assert generator.name == name
    assert generator.title
    assert generator.purpose
