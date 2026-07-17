"""Tests for the GraphStore abstraction - in-memory (always run) and Neo4j (opt-in)."""
from src.storage.memory_graph_store import InMemoryGraphStore


def test_memory_store_upsert_is_idempotent_per_site():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "a.com/x", status="Pending", components=0)
    store.upsert_page("a.com", "a.com/x", status="Finished", components=5)
    # A later bare rediscovery must not clobber the Finished status/components.
    store.upsert_page("a.com", "a.com/x", status="Pending", components=0)

    rows = store.get_progress_table_rows("a.com")
    assert len(rows) == 1
    assert rows[0]["status"] == "Finished"
    assert rows[0]["components"] == 5


def test_memory_store_is_visited_false_for_unknown_url():
    store = InMemoryGraphStore()
    assert store.is_visited("a.com", "a.com/never-seen") is False


def test_memory_store_pending_respects_limit_and_order():
    store = InMemoryGraphStore()
    for i in (3, 1, 2):
        store.upsert_page("a.com", f"a.com/page-{i}")

    assert store.get_pending("a.com") == ["a.com/page-1", "a.com/page-2", "a.com/page-3"]
    assert store.get_pending("a.com", limit=2) == ["a.com/page-1", "a.com/page-2"]


def test_memory_store_site_isolation():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "shared/path", status="Pending")
    store.upsert_page("b.com", "shared/path", status="Finished")

    assert store.is_visited("a.com", "shared/path") is False
    assert store.is_visited("b.com", "shared/path") is True
    assert store.get_pending("a.com") == ["shared/path"]
    assert store.get_pending("b.com") == []

    store.record_edge("a.com", "a.com/home", "a.com/about", "link", "GOTO a.com/about")
    store.record_edge("b.com", "b.com/home", "b.com/about", "link", "GOTO b.com/about")
    assert len(store.get_edges("a.com")) == 1
    assert len(store.get_edges("b.com")) == 1
    assert store.get_edges("a.com")[0]["to"] == "a.com/about"
    assert store.get_edges("b.com")[0]["to"] == "b.com/about"


def test_memory_store_link_label_is_scoped_to_the_specific_from_to_pair():
    store = InMemoryGraphStore()
    store.record_link("a.com", "a.com/home", "a.com/about", "About Us")
    store.record_link("a.com", "a.com/other-page", "a.com/about", "Learn more")

    assert store.get_link_label("a.com", "a.com/home", "a.com/about") == "About Us"
    assert store.get_link_label("a.com", "a.com/other-page", "a.com/about") == "Learn more"
    # No link was ever recorded from this page to /about - must not fall back
    # to any label discovered via a different source page.
    assert store.get_link_label("a.com", "a.com/unrelated-page", "a.com/about") is None


def test_memory_store_loop_signals_detects_revisit():
    store = InMemoryGraphStore()
    store.record_edge("a.com", "a.com/home", "a.com/contact", "link \"Contact\"", "GOTO a.com/contact")
    store.record_edge("a.com", "a.com/about", "a.com/contact", "link \"Contact us\"", "GOTO a.com/contact")

    signals = store.get_loop_signals("a.com", "a.com/contact")
    assert len(signals) == 2
    assert {"component": 'link "Contact"', "from": "a.com/home"} in signals

    assert store.get_loop_signals("a.com", "a.com/never-reached") == []


def test_generator_uses_injected_graph_store(tmp_path):
    from src.core.engine import Engine
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    store = InMemoryGraphStore()
    agent = ScriptedAgent(["plan", "GOTO https://stub/page-a", "FINISH"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, graph_store=store, progress_file=str(tmp_path / "progress.md"), max_iterations=3
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert store is gen.graph_store
    assert len(store.get_edges(gen.base_domain)) == 1
