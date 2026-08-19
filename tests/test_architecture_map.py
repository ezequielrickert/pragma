"""Unit tests for the architecture map (generators/architecture_map.py).
Pure functions over hand-built metric rows - no store, no model."""
from generators.architecture_map import (
    ArchitectureMapDocument,
    hosts_by_traffic,
    summarize_modules,
)


def _page(url, module_id=None, module_label="", click_depth=None, articulation=False):
    return {
        "url": url, "module_id": module_id, "module_label": module_label,
        "click_depth": click_depth, "is_articulation_point": articulation,
        "in_degree": 0, "out_degree": 0, "betweenness": 0.0, "pagerank": 0.0,
    }


class _Store:
    def __init__(self, metrics, integrations=()):
        self._metrics = metrics
        self._integrations = list(integrations)

    def get_page_metrics(self):
        return self._metrics

    def integrations(self):
        return self._integrations


class _Request:
    def __init__(self, store):
        self.graph_store = store
        self.site = "shop.example"


# --- modules ---

def test_modules_are_ordered_by_how_many_pages_they_hold():
    summaries = summarize_modules([
        _page("https://x/a", module_id=1, module_label="small", click_depth=0),
        _page("https://x/b", module_id=2, module_label="big", click_depth=1),
        _page("https://x/c", module_id=2, module_label="big", click_depth=2),
    ])

    assert [s.label for s in summaries] == ["big", "small"]


def test_the_shallowest_page_is_the_modules_front_door():
    summaries = summarize_modules([
        _page("https://x/deep", module_id=1, module_label="shop", click_depth=4),
        _page("https://x/door", module_id=1, module_label="shop", click_depth=1),
    ])

    assert summaries[0].entry_page == "https://x/door"
    assert (summaries[0].shallowest_depth, summaries[0].deepest_depth) == (1, 4)


def test_a_module_whose_pages_are_all_unreachable_reports_no_depth():
    summaries = summarize_modules([_page("https://x/a", module_id=1, module_label="orphaned")])

    assert summaries[0].shallowest_depth is None
    assert summaries[0].deepest_depth is None


def test_a_page_in_no_module_is_not_pooled_into_a_synthetic_one():
    """The module table answers "what parts exist"; a page belonging to no
    part is not a part. The depth table still counts it."""
    assert summarize_modules([_page("https://x/loner", click_depth=2)]) == []


def test_a_module_with_no_label_falls_back_to_its_id():
    summaries = summarize_modules([_page("https://x/a", module_id=9, module_label="")])

    assert summaries[0].label == "Module 9"


def test_articulation_points_are_reported_per_module():
    summaries = summarize_modules([
        _page("https://x/hub", module_id=1, module_label="shop", click_depth=1, articulation=True),
        _page("https://x/leaf", module_id=1, module_label="shop", click_depth=2),
    ])

    assert summaries[0].articulation_points == ("https://x/hub",)


# --- third-party hosts ---

def test_endpoints_are_summed_per_host_busiest_first():
    hosts = hosts_by_traffic([
        {"host": "analytics.example", "method": "POST", "path_pattern": "/t", "call_count": 3},
        {"host": "pay.example", "method": "POST", "path_pattern": "/charge", "call_count": 40},
        {"host": "pay.example", "method": "GET", "path_pattern": "/status", "call_count": 2},
    ])

    assert hosts == [("pay.example", 42, 2), ("analytics.example", 3, 1)]


def test_a_missing_host_is_labelled_not_dropped():
    assert hosts_by_traffic([{"method": "GET", "path_pattern": "/x", "call_count": 1}]) == [
        ("(unknown host)", 1, 1)
    ]


# --- the document ---

def test_the_document_reports_modules_bottlenecks_depth_and_integrations():
    store = _Store(
        [_page("https://x/hub", module_id=1, module_label="shop", click_depth=0, articulation=True)],
        [{"host": "pay.example", "method": "POST", "path_pattern": "/charge", "call_count": 4}],
    )

    text = ArchitectureMapDocument().generate(_Request(store))

    assert "## Modules" in text
    assert "https://x/hub" in text
    assert "no alternate route around them" in text
    assert "pay.example" in text
    assert "Navigation cycles" in text


def test_a_site_with_no_pages_says_so_instead_of_rendering_empty_tables():
    text = ArchitectureMapDocument().generate(_Request(_Store([])))

    assert "no structure to describe" in text
    assert "## Modules" not in text


def test_pages_with_no_module_still_produce_a_depth_table():
    """A crawl whose projection never ran must still say something true."""
    text = ArchitectureMapDocument().generate(_Request(_Store([_page("https://x/a", click_depth=0)])))

    assert "No modules were detected" in text
    assert "## How deep it goes" in text


def test_unreachable_pages_are_counted_and_explained():
    text = ArchitectureMapDocument().generate(
        _Request(_Store([_page("https://x/orphan", module_id=1, module_label="m")]))
    )

    assert "not reachable from the entry point" in text


def test_no_third_party_traffic_is_stated_rather_than_left_blank():
    text = ArchitectureMapDocument().generate(
        _Request(_Store([_page("https://x/a", module_id=1, module_label="m", click_depth=0)]))
    )

    assert "No third-party HTTP traffic was observed" in text
