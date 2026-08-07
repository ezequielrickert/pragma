"""Tests for Fase 2: sitemap seeding, and breadth-first-then-priority ordering of
Pending routes (SimplePRDGenerator._seed_from_sitemap / _order_pending /
_top_level_section, GraphStore.get_incoming_link_counts)."""
from unittest.mock import patch

from src.generators.prd_generator import SimplePRDGenerator
from src.storage.memory_graph_store import InMemoryGraphStore
from tests.test_imports import ScriptedAgent, StubScraper


def _gen(tmp_path, **kwargs) -> SimplePRDGenerator:
    gen = SimplePRDGenerator(
        ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"), **kwargs
    )
    gen.base_domain = "a.com"
    return gen


class _FakeResponse:
    def __init__(self, content: bytes, ok: bool = True):
        self.content = content
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("404")


_URLSET_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://a.com/menu</loc></url>
  <url><loc>https://a.com/about</loc></url>
  <url><loc>https://other.com/ignored</loc></url>
</urlset>"""

_INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://a.com/sitemap-a.xml</loc></sitemap>
  <sitemap><loc>https://a.com/sitemap-b.xml</loc></sitemap>
</sitemapindex>"""

_SUB_A_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://a.com/product-1</loc></url>
</urlset>"""

_SUB_B_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://a.com/product-2</loc></url>
</urlset>"""


def test_use_sitemap_defaults_to_false_and_never_calls_requests(tmp_path):
    """Deliberate safety default (see SimplePRDGenerator.__init__'s docstring) -
    must not make a real network call unless explicitly opted into."""
    gen = _gen(tmp_path)
    with patch("src.generators.prd_generator.requests.get") as mock_get:
        gen._seed_from_sitemap("https://a.com")
        mock_get.assert_not_called()
    assert gen.graph_store.get_pending("a.com") == []


def test_seed_from_sitemap_queues_in_scope_urls_only(tmp_path):
    gen = _gen(tmp_path, use_sitemap=True)
    with patch("src.generators.prd_generator.requests.get", return_value=_FakeResponse(_URLSET_XML)):
        gen._seed_from_sitemap("https://a.com")

    pending = gen.graph_store.get_pending("a.com")
    assert pending == ["a.com/about", "a.com/menu"]
    # other.com is out of scope - must never be queued.
    assert "other.com/ignored" not in pending


def test_seed_from_sitemap_follows_one_level_of_sitemap_index(tmp_path):
    gen = _gen(tmp_path, use_sitemap=True)

    def fake_get(url, timeout=5):
        return {
            "https://a.com/sitemap.xml": _FakeResponse(_INDEX_XML),
            "https://a.com/sitemap-a.xml": _FakeResponse(_SUB_A_XML),
            "https://a.com/sitemap-b.xml": _FakeResponse(_SUB_B_XML),
        }[url]

    with patch("src.generators.prd_generator.requests.get", side_effect=fake_get):
        gen._seed_from_sitemap("https://a.com")

    assert gen.graph_store.get_pending("a.com") == ["a.com/product-1", "a.com/product-2"]


def test_seed_from_sitemap_is_best_effort_on_failure(tmp_path):
    """A missing/unreachable sitemap (very common - not every site has one) must
    never raise or block the run - just means nothing gets seeded."""
    gen = _gen(tmp_path, use_sitemap=True)
    with patch("src.generators.prd_generator.requests.get", side_effect=RuntimeError("connection refused")):
        gen._seed_from_sitemap("https://a.com")  # must not raise

    assert gen.graph_store.get_pending("a.com") == []


def test_top_level_section():
    assert SimplePRDGenerator._top_level_section("a.com") == ""
    assert SimplePRDGenerator._top_level_section("a.com/menu") == "menu"
    assert SimplePRDGenerator._top_level_section("a.com/menu/empanadas") == "menu"


def test_order_pending_skeleton_phase_prefers_unvisited_sections(tmp_path):
    """During the skeleton phase, a route under a section with no Finished page
    yet must be surfaced ahead of one under an already-Finished section."""
    gen = _gen(tmp_path, max_iterations=10, skeleton_fraction=0.5)  # skeleton_iterations = 5
    gen.graph_store.upsert_page("a.com", "a.com/menu", status="Finished")
    gen._completed_iterations = 0  # still inside the skeleton phase (0 < 5)

    ordered = gen._order_pending(["a.com/menu/postres", "a.com/contacto", "a.com/menu/pizza"])

    # Both "contacto" (a brand-new section) come before either "menu/*" route
    # (menu is already Finished) - stable sort keeps the two menu/* routes in
    # their original relative order.
    assert ordered == ["a.com/contacto", "a.com/menu/postres", "a.com/menu/pizza"]


def test_order_pending_depth_phase_ranks_by_incoming_link_count(tmp_path):
    gen = _gen(tmp_path, max_iterations=10, skeleton_fraction=0.2)  # skeleton_iterations = 2
    gen._completed_iterations = 5  # past the skeleton phase (5 >= 2)
    gen.graph_store.record_link("a.com", "a.com/home", "a.com/popular", "Popular")
    gen.graph_store.record_link("a.com", "a.com/menu", "a.com/popular", "Popular")
    gen.graph_store.record_link("a.com", "a.com/home", "a.com/rare", "Rare")

    ordered = gen._order_pending(["a.com/rare", "a.com/popular", "a.com/unlinked"])

    # popular has 2 distinct incoming links, rare has 1, unlinked has 0 (never
    # linked to yet, e.g. seeded straight from the sitemap) and sorts last.
    assert ordered == ["a.com/popular", "a.com/rare", "a.com/unlinked"]


def test_order_pending_never_drops_a_route(tmp_path):
    """Purely advisory reordering - every route that went in must still come out,
    regardless of phase."""
    gen = _gen(tmp_path)
    pending = ["a.com/x", "a.com/y", "a.com/z"]
    assert set(gen._order_pending(pending)) == set(pending)


def test_memory_store_get_incoming_link_counts():
    store = InMemoryGraphStore()
    store.record_link("a.com", "a.com/home", "a.com/popular", "Popular")
    store.record_link("a.com", "a.com/menu", "a.com/popular", "Popular")
    store.record_link("a.com", "a.com/home", "a.com/rare", "Rare")
    # A second link from the *same* source to the same destination must not
    # double-count - it's the number of distinct sources, not raw link records.
    store.record_link("a.com", "a.com/home", "a.com/popular", "Also popular")

    counts = store.get_incoming_link_counts("a.com")
    assert counts == {"a.com/popular": 2, "a.com/rare": 1}
