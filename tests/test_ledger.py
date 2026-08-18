"""Unit tests for generators/ledger.py - built directly against
LadybugGraphStore in-memory mode, same convention as tests/test_graph_export.py
(flat_component_ledger only touches the store's read surface)."""
from generators.ledger import flat_component_ledger
from database.ladybug.store import LadybugGraphStore

SITE = "ledger-test-site"
PAGE = "example.com/catalog"
OTHER_PAGE = "example.com/cart"


def _store():
    store = LadybugGraphStore(SITE)
    store.connect()
    return store


def test_flat_component_ledger_is_empty_for_an_unknown_site():
    assert flat_component_ledger(_store()) == []


def test_flat_component_ledger_folds_page_url_and_path_into_each_row():
    store = _store()
    store.record_component(PAGE, "div > button", tag="button", text="Add")

    rows = flat_component_ledger(store)

    assert len(rows) == 1
    assert rows[0]["page_url"] == PAGE
    assert rows[0]["path"] == "div > button"
    assert rows[0]["text"] == "Add"


def test_flat_component_ledger_flattens_across_pages():
    """The whole point: one list, not one dict per page - a whole-site pass
    reasons about look-alike components wherever they live."""
    store = _store()
    store.record_component(PAGE, "div > button", tag="button", text="Add")
    store.record_component(OTHER_PAGE, "div > button", tag="button", text="Remove")

    rows = flat_component_ledger(store)

    assert {(row["page_url"], row["text"]) for row in rows} == {
        (PAGE, "Add"),
        (OTHER_PAGE, "Remove"),
    }


def test_flat_component_ledger_keeps_the_interaction_record():
    """`build_traces` reads `interactions` off these rows, so the flattening
    must not drop anything the ledger recorded."""
    store = _store()
    store.record_component(PAGE, "div > button", tag="button", text="Buy")
    store.record_component_interaction(PAGE, "div > button", "click")

    row = flat_component_ledger(store)[0]

    assert row["interacted"] is True
    assert len(row["interactions"]) == 1
    assert row["interactions"][0]["action"] == "click"
