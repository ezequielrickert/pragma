"""Unit tests for GraphStoreSink's dropdown/choice-group node consolidation
(component_classifier.group_option_families + GraphStoreSink._record_choice_group
/_resolve_write_path). Calls GraphStoreSink directly against InMemoryGraphStore
with synthetic component dicts - no browser/crawl needed, same pattern as
tests/test_graph_sink_tracker_cache.py.

GraphStoreSink's write methods are async (see graph_sink.py's `_write` -
every write is offloaded via asyncio.to_thread so it doesn't block the crawl's
event loop), so each test wraps its calls in asyncio.run() directly, matching
tests/test_crawl4ai_crawler.py's no-pytest-asyncio-dependency convention.
"""
import asyncio

from spiders.graph_sink import GraphStoreSink
from generators.component_classifier import describe_options
from database.memory_graph_store import InMemoryGraphStore

SITE = "consolidation-test-site"
PAGE = "example.com"


def _sink() -> GraphStoreSink:
    store = InMemoryGraphStore()
    store.connect()
    store.upsert_page(SITE, PAGE, status="Pending")
    return GraphStoreSink(store, SITE)


def _dropdown_components():
    """A 3-option ARIA dropdown - the shape discover_components.js produces
    for a Radix/react-select-style combobox popover."""
    return [
        {"tag": "button", "role": "combobox", "text": "Choose a size", "path": "button#sizeTrigger", "rect": {}},
        {"tag": "div", "role": "option", "text": "Small", "path": "div#sizeList > div:nth-of-type(1)", "rect": {}},
        {"tag": "div", "role": "option", "text": "Medium", "path": "div#sizeList > div:nth-of-type(2)", "rect": {}},
        {"tag": "div", "role": "option", "text": "Large", "path": "div#sizeList > div:nth-of-type(3)", "rect": {}},
    ]


def test_dropdown_options_collapse_into_one_component_node():
    sink = _sink()
    asyncio.run(sink.record_inventory(PAGE, _dropdown_components(), links=[]))

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    option_texts = {c["text"] for c in ledger.values() if c["text"] in ("Small", "Medium", "Large")}
    assert option_texts == {"Small"}, "3 options must collapse into 1 representative node, not 3"

    parsed = describe_options(ledger["div#sizeList > div:nth-of-type(1)"]["options"])
    assert parsed["kind"] == "choice_group"
    assert {c["text"] for c in parsed["choices"]} == {"Small", "Medium", "Large"}

    # The trigger button is a normal, ungrouped component - untouched.
    assert ledger["button#sizeTrigger"]["text"] == "Choose a size"


def test_radio_group_sharing_a_name_also_collapses_into_one_node():
    components = [
        {"tag": "input", "input_type": "radio", "name": "size", "text": "Small", "path": "input#s", "rect": {}},
        {"tag": "input", "input_type": "radio", "name": "size", "text": "Large", "path": "input#l", "rect": {}},
    ]
    sink = _sink()
    asyncio.run(sink.record_inventory(PAGE, components, links=[]))

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    assert set(ledger.keys()) == {"input#s"}, "the 2 radios must collapse into 1 representative node"


def test_ungrouped_components_are_unaffected():
    """A lone button and a lone (singleton) role=option must each keep their
    own node - consolidation only kicks in for an actual multi-member list."""
    components = [
        {"tag": "button", "text": "Submit", "path": "button#submit", "rect": {}},
        {"tag": "div", "role": "option", "text": "Only choice", "path": "div#x > div", "rect": {}},
    ]
    sink = _sink()
    asyncio.run(sink.record_inventory(PAGE, components, links=[]))

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    assert set(ledger.keys()) == {"button#submit", "div#x > div"}


def test_interacting_with_a_non_representative_option_redirects_not_creates_a_node():
    sink = _sink()

    async def run():
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])
        await sink.record_interaction(PAGE, "div#sizeList > div:nth-of-type(3)", "click", value="", resulting_url="")

    asyncio.run(run())

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    assert "div#sizeList > div:nth-of-type(3)" not in ledger, "clicking 'Large' must not create its own node"

    representative = ledger["div#sizeList > div:nth-of-type(1)"]
    assert representative["interacted"] is True
    interaction = representative["interactions"][0]
    assert interaction["source_path"] == "div#sizeList > div:nth-of-type(3)", (
        "which option actually acted must be recorded on the group's node, not lost"
    )


def test_interacting_with_the_representative_option_itself_carries_no_source_path():
    """When the member that acts happens to be the representative, there's
    nothing to redirect - source_path stays blank, same as any ordinary
    (ungrouped) interaction. It is present-and-empty rather than absent
    since interactions moved onto :INTERACTED relationships, where every
    property exists on every edge; every reader treats "" as absent."""
    sink = _sink()

    async def run():
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])
        await sink.record_interaction(PAGE, "div#sizeList > div:nth-of-type(1)", "click", value="", resulting_url="")

    asyncio.run(run())

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    interaction = ledger["div#sizeList > div:nth-of-type(1)"]["interactions"][0]
    assert interaction["source_path"] == ""


def test_network_requests_on_a_non_representative_option_redirect_and_are_tagged():
    sink = _sink()

    async def run():
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])
        await sink.record_component_network(
            PAGE, "div#sizeList > div:nth-of-type(2)",
            [{"method": "GET", "url": "/api/sizes/medium", "resource_type": "fetch", "status": 200, "failed": False}],
        )

    asyncio.run(run())

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    assert "div#sizeList > div:nth-of-type(2)" not in ledger
    requests = ledger["div#sizeList > div:nth-of-type(1)"]["network_requests"]
    assert requests[0]["source_path"] == "div#sizeList > div:nth-of-type(2)"


def test_navigation_edge_still_carries_the_raw_option_path_not_the_representative():
    """record_navigation_edge is untouched by consolidation - a Page-to-Page
    edge is never a Component node in the first place, so there's nothing to
    redirect; it should keep naming exactly which option caused it."""
    sink = _sink()

    async def run():
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])
        sink.graph_store.upsert_page(SITE, "example.com/large-details", status="Pending")
        await sink.record_navigation_edge(
            PAGE, "example.com/large-details", "div#sizeList > div:nth-of-type(3)", "click"
        )

    asyncio.run(run())

    edges = sink.graph_store.get_edges(SITE)
    assert edges[0]["component"] == "div#sizeList > div:nth-of-type(3)"
    assert edges[0]["to"] == "example.com/large-details"


def test_repeated_inventory_passes_do_not_forget_earlier_group_membership():
    """record_inventory runs again on every same-page reveal - a later pass
    that (for whatever reason) is given a narrower component list must not
    lose the earlier pass's redirect mapping for paths it already grouped."""
    sink = _sink()

    async def run():
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])
        await sink.record_inventory(PAGE, _dropdown_components(), links=[])  # second pass, same shape
        await sink.record_interaction(PAGE, "div#sizeList > div:nth-of-type(2)", "click", value="", resulting_url="")

    asyncio.run(run())

    ledger = sink.graph_store.get_component_ledger(SITE)[PAGE]
    assert "div#sizeList > div:nth-of-type(2)" not in ledger
