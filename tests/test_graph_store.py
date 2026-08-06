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


def test_memory_store_clear_site_removes_only_that_site():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "a.com/x", status="Finished")
    store.record_edge("a.com", "a.com/home", "a.com/x", "link", "GOTO a.com/x")
    store.upsert_page("b.com", "b.com/x", status="Finished")

    store.clear_site("a.com")

    assert store.get_progress_table_rows("a.com") == []
    assert store.get_edges("a.com") == []
    # Untouched: clear_site is scoped to the one site, not a global reset.
    assert store.is_visited("b.com", "b.com/x") is True


def test_memory_store_record_component_is_idempotent_and_preserves_interacted():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#go", tag="button", text="Go")
    store.record_component_interaction("a.com", "a.com/x", "button#go", action="click")
    # A later rediscovery (e.g. the page is revisited) must not clobber the
    # interacted flag or its interaction history - only descriptive fields
    # (tag/text/etc.) refresh, same discipline as upsert_page's Pending-never-
    # clobbers-Finished rule.
    store.record_component("a.com", "a.com/x", "button#go", tag="button", text="Go (updated)")

    states = store.get_component_states("a.com", "a.com/x")
    assert states["button#go"]["interacted"] is True
    assert states["button#go"]["text"] == "Go (updated)"


def test_memory_store_record_component_interaction_auto_creates_node():
    store = InMemoryGraphStore()
    store.record_component_interaction("a.com", "a.com/x", "button#go", action="click", value="", resulting_url="a.com/y")

    states = store.get_component_states("a.com", "a.com/x")
    assert states["button#go"]["interacted"] is True

    ledger = store.get_component_ledger("a.com")
    assert ledger["a.com/x"]["button#go"]["interactions"] == [
        {"action": "click", "value": "", "resulting_url": "a.com/y"}
    ]


def test_memory_store_count_unexplored_components_respects_semantic_only():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a", layer="semantic")
    store.record_component("a.com", "a.com/x", "div#b", layer="pointer")

    assert store.count_unexplored_components("a.com", semantic_only=True) == (1, 1)
    assert store.count_unexplored_components("a.com", semantic_only=False) == (2, 2)

    store.record_component_interaction("a.com", "a.com/x", "button#a", action="click")
    assert store.count_unexplored_components("a.com", semantic_only=True) == (0, 1)


def test_memory_store_page_has_unexplored_components():
    store = InMemoryGraphStore()
    assert store.page_has_unexplored_components("a.com", "a.com/x") is False

    store.record_component("a.com", "a.com/x", "button#a")
    assert store.page_has_unexplored_components("a.com", "a.com/x") is True

    store.record_component_interaction("a.com", "a.com/x", "button#a", action="click")
    assert store.page_has_unexplored_components("a.com", "a.com/x") is False


def test_memory_store_get_pages_with_unexplored_components_sorted_descending():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a")
    store.record_component("a.com", "a.com/y", "button#b")
    store.record_component("a.com", "a.com/y", "button#c")
    # Fully explored - must not appear in the debt list at all.
    store.record_component("a.com", "a.com/z", "button#d")
    store.record_component_interaction("a.com", "a.com/z", "button#d", action="click")

    rows = store.get_pages_with_unexplored_components("a.com")
    assert rows == [
        {"url": "a.com/y", "unexplored_count": 2},
        {"url": "a.com/x", "unexplored_count": 1},
    ]


def test_memory_store_clear_site_removes_components_too():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a")
    store.clear_site("a.com")

    assert store.get_component_states("a.com", "a.com/x") == {}
    assert store.count_unexplored_components("a.com") == (0, 0)


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


class _SpyGraphStore(InMemoryGraphStore):
    """Records clear_site calls without needing a live Neo4j instance -
    exercises Engine.from_config's PragmaConfig.fresh wiring directly."""

    def __init__(self) -> None:
        super().__init__()
        self.cleared_sites: list = []

    def clear_site(self, site: str) -> None:
        self.cleared_sites.append(site)
        super().clear_site(site)


def test_engine_from_config_clears_site_when_fresh(tmp_path):
    from src.core.config import PragmaConfig
    from src.core.engine import Engine
    from src.core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", scraper="playwright", agent="mock",
        graph_store="_spy_fresh_test", out_dir=str(tmp_path), logs_dir=str(tmp_path),
        progress_logs_dir=str(tmp_path), graph_logs_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert isinstance(engine.graph_store, _SpyGraphStore)
    assert engine.graph_store.cleared_sites == ["stub.example"]


def test_engine_from_config_skips_clear_when_not_fresh(tmp_path):
    from src.core.config import PragmaConfig
    from src.core.engine import Engine
    from src.core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_no_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", scraper="playwright", agent="mock",
        graph_store="_spy_no_fresh_test", fresh=False, out_dir=str(tmp_path), logs_dir=str(tmp_path),
        progress_logs_dir=str(tmp_path), graph_logs_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert engine.graph_store.cleared_sites == []
