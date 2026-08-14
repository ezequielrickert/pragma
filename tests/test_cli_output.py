"""Unit tests for the CLI's end-of-run document listing (cli.py).
Pure formatting over an EngineRunResult - no crawl, no browser, no disk."""
from cli import _print_documents
from core.documents import ProducedDocument
from core.engine import EngineRunResult

TIMESTAMP = "20260812T210000Z"


def _result(*names):
    titles = {
        "coverage": "Crawl Coverage",
        "prd": "Digital Blueprint",
        "tree": "Component Tree",
        "master": "Start Here",
    }
    documents = tuple(
        ProducedDocument(name, titles[name], "...", f"docs/site_{name}_{TIMESTAMP}.md") for name in names
    )
    return EngineRunResult(prd_path="", tree_path="", documents=documents)


def test_master_document_is_listed_first(capsys):
    """It indexes the others and carries the coverage numbers, so it is the
    one to open - buried in the list it is just another filename."""
    _print_documents(_result("coverage", "prd", "tree", "master"))

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]

    assert lines[0] == f"Start here -> docs/site_master_{TIMESTAMP}.md"


def test_every_document_is_listed(capsys):
    """The listing iterates result.documents, so a document added by a later
    phase appears without this code changing."""
    _print_documents(_result("coverage", "prd", "tree", "master"))

    out = capsys.readouterr().out

    for name in ("coverage", "prd", "tree", "master"):
        assert f"docs/site_{name}_{TIMESTAMP}.md" in out


def test_master_is_not_repeated_in_the_indented_list(capsys):
    _print_documents(_result("coverage", "master"))

    out = capsys.readouterr().out

    assert out.count(f"docs/site_master_{TIMESTAMP}.md") == 1


def test_a_run_that_produced_nothing_says_so(capsys):
    """Every generator failing is survivable by design (the pipeline degrades
    per document); printing an empty list would look like success."""
    _print_documents(EngineRunResult(prd_path="", tree_path=""))

    assert "No documents were generated" in capsys.readouterr().out
