"""Regression tests for issue #62: a mutation the mode-gate handler blocks
(method-based or GET-heuristic-based) must land on the corresponding
`Interaction` node's `blocked`/`blocked_reason` columns, and an on-disk
database created before those columns existed must pick them up on the
next `connect()`.

Split three ways, cheapest first: the migration itself (a fresh Kùzu table
missing the columns, no crawl/sink involved), the graph-store write path
(`LadybugGraphStore.record_component_interaction`, in-memory, no browser -
same pattern as `tests/test_graph_sink_consolidation.py`), and
`PageVisitor`'s own `_blocked_summary` helper (pure Python, no store at
all). The full hooks -> PageState -> sink -> store pipeline is already
covered at the network layer by `tests/test_mode_gate.py`; this file
covers what happens to a block *after* the network layer, not whether one
was correctly triggered.
"""
from __future__ import annotations

import asyncio

from database.ladybug.schema import DDL
from database.ladybug.store import LadybugGraphStore, _migrate_interaction_blocked_columns
from database.ladybug.writer import LadybugWriter
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.page_visitor.visitor import _blocked_summary

SITE = "blocked-mutation-test-site"
PAGE = "example.com"

# `DDL` minus the two `blocked`/`blocked_reason` columns - a stand-in for an
# `.lbdb` file created before issue #62, without needing an actual file on
# disk (the in-memory engine is enough to prove the migration statement
# itself works against a table that predates it).
_PRE_MIGRATION_INTERACTION_DDL = """
CREATE NODE TABLE IF NOT EXISTS Interaction(
    id SERIAL PRIMARY KEY,
    action STRING DEFAULT '',
    value STRING DEFAULT '',
    source_path STRING DEFAULT '',
    visit_id STRING DEFAULT '',
    step_seq INT64 DEFAULT 0);
"""


def _sink() -> GraphStoreSink:
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page(PAGE, status="Pending")
    return GraphStoreSink(store)


def test_migration_adds_columns_to_a_pre_existing_interaction_table() -> None:
    writer = LadybugWriter("")
    try:
        writer.call(lambda conn: conn.execute(_PRE_MIGRATION_INTERACTION_DDL))
        writer.call(lambda conn: conn.execute("CREATE (:Interaction {action: 'click'})"))

        writer.call(_migrate_interaction_blocked_columns)

        rows = list(writer.call(
            lambda conn: conn.execute("MATCH (i:Interaction) RETURN i.blocked, i.blocked_reason")
        ))
        assert rows == [[False, ""]]
    finally:
        writer.close()


def test_migration_is_a_no_op_against_a_table_that_already_has_the_columns() -> None:
    writer = LadybugWriter("")
    try:
        writer.call(lambda conn: conn.execute(DDL))

        writer.call(_migrate_interaction_blocked_columns)  # must not raise
    finally:
        writer.close()


def test_connect_runs_the_migration_on_a_pre_existing_database(tmp_path) -> None:
    """A real `.lbdb` file, created by hand with the pre-#62 `Interaction`
    shape, then opened by `LadybugGraphStore.connect()` the ordinary way -
    the exact scenario `_migrate_interaction_blocked_columns`'s docstring
    describes, exercised end-to-end rather than just the migration
    statement in isolation."""
    directory = str(tmp_path)
    old_writer = LadybugWriter(f"{directory}/{SITE}.lbdb")
    try:
        old_writer.call(lambda conn: conn.execute(_PRE_MIGRATION_INTERACTION_DDL))
        old_writer.call(lambda conn: conn.execute("CREATE (:Interaction {action: 'click'})"))
    finally:
        old_writer.close()

    store = LadybugGraphStore(SITE, directory=directory)
    try:
        store.connect()  # must not raise against the pre-#62 file
        store.upsert_page(PAGE, status="Pending")
        store.record_component_interaction(PAGE, "#btn", "click", blocked=True, blocked_reason="POST")
        evidence = store.get_interaction_evidence()
        # Only this write's own row - the pre-existing one is a bare
        # `Interaction` with no `PERFORMED` edge, so get_interaction_evidence's
        # Component/Page join can't see it at all. What this test actually
        # proves is narrower: connect() against the old file didn't raise.
        assert len(evidence) == 1
    finally:
        store.close()


def test_record_component_interaction_persists_blocked_flag() -> None:
    store = LadybugGraphStore(SITE)
    store.connect()
    try:
        store.upsert_page(PAGE, status="Pending")
        store.record_component_interaction(
            PAGE, "#deleteButton", "click", blocked=True, blocked_reason="DELETE"
        )

        def op(conn):
            return list(conn.execute(
                "MATCH (i:Interaction {action: 'click'}) RETURN i.blocked, i.blocked_reason"
            ))

        rows = store._call(op)
        assert rows == [[True, "DELETE"]]
    finally:
        store.close()


def test_record_component_interaction_defaults_to_not_blocked() -> None:
    store = LadybugGraphStore(SITE)
    store.connect()
    try:
        store.upsert_page(PAGE, status="Pending")
        store.record_component_interaction(PAGE, "#link", "click")

        def op(conn):
            return list(conn.execute(
                "MATCH (i:Interaction {action: 'click'}) RETURN i.blocked, i.blocked_reason"
            ))

        rows = store._call(op)
        assert rows == [[False, ""]]
    finally:
        store.close()


def test_sink_record_interaction_passes_blocked_flag_through_to_the_store() -> None:
    sink = _sink()
    try:
        asyncio.run(sink.record_interaction(
            PAGE, "#createForm button[type=submit]", "click", value="", resulting_url="",
            blocked=True, blocked_reason="POST",
        ))

        def op(conn):
            return list(conn.execute(
                "MATCH (i:Interaction {action: 'click'}) RETURN i.blocked, i.blocked_reason"
            ))

        rows = sink.graph_store._call(op)
        assert rows == [[True, "POST"]]
    finally:
        sink.graph_store.close()


def test_blocked_summary_of_no_blocked_mutations_is_not_blocked() -> None:
    assert _blocked_summary([]) == (False, "")


def test_blocked_summary_reports_the_blocked_method() -> None:
    assert _blocked_summary([{"method": "POST", "url": "https://x/api/items"}]) == (True, "POST")


def test_blocked_summary_dedupes_and_sorts_multiple_blocked_methods() -> None:
    blocked_mutations = [
        {"method": "DELETE", "url": "https://x/api/items/1"},
        {"method": "POST", "url": "https://x/api/items"},
        {"method": "DELETE", "url": "https://x/api/items/2"},
    ]

    assert _blocked_summary(blocked_mutations) == (True, "DELETE,POST")
