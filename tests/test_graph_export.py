"""Unit tests for generators/graph_export.py - built directly against
LadybugGraphStore in-memory mode, same convention as
tests/test_document_pipeline.py (build_export_graph only touches the
store's read surface)."""
import json

from core.documents import DocumentRequest
from database.ladybug.store import LadybugGraphStore
from generators.graph_export import _token_nodes, build_export_graph

SITE = "export-test-site"


class StubAgent:
    def generate(self, prompt, system_instruction=None):
        return "STUB"


def _request(store, run_id="20260820T000000Z"):
    return DocumentRequest(graph_store=store, site=SITE, agent=StubAgent(), settings={"run_id": run_id})


def _store():
    store = LadybugGraphStore(SITE)
    store.connect()
    return store


def _node(document, node_id):
    return next(node for node in document["@graph"] if node["id"] == node_id)


def test_pages_become_pantalla_nodes_containing_their_components():
    store = _store()
    store.upsert_page("example.com/", status="Finished", title="Home")
    store.record_component("example.com/", "a.about", tag="a", text="About")

    document = build_export_graph(_request(store))

    page = _node(document, "example.com/")
    assert page["type"] == "Pantalla"
    assert page["label"] == "Home"
    assert page["contiene"] == [f"example.com/|a.about"]
    component = _node(document, "example.com/|a.about")
    assert component["type"] == "Componente"
    assert component["label"] == "About"


def test_external_pages_get_no_pantalla_node_and_no_dangling_edge():
    """A link this crawl only discovered, never visited, is not a screen
    of the application - docs/dev/database/ladybug/page.md's own
    count_visited exclusion, applied here too."""
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("other.example", status="External")
    store.record_component("example.com/", "a.out", tag="a")
    store.record_edge("example.com/", "other.example", component="a.out", action="click")

    document = build_export_graph(_request(store))

    ids = {node["id"] for node in document["@graph"]}
    assert "other.example" not in ids
    component = _node(document, "example.com/|a.out")
    assert "navega_a" not in component


def test_navigation_via_a_component_attributes_the_edge_to_it():
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("example.com/about", status="Finished")
    store.record_component("example.com/", "a.about", tag="a")
    store.record_edge("example.com/", "example.com/about", component="a.about", action="click")

    document = build_export_graph(_request(store))

    component = _node(document, "example.com/|a.about")
    assert component["navega_a"] == ["example.com/about"]
    page = _node(document, "example.com/")
    assert "navega_a" not in page


def test_navigation_with_no_component_attributes_the_edge_to_the_page():
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("example.com/redirected", status="Finished")
    store.record_edge("example.com/", "example.com/redirected", component="", action="redirect")

    document = build_export_graph(_request(store))

    page = _node(document, "example.com/")
    assert page["navega_a"] == ["example.com/redirected"]


def test_endpoints_are_populated_with_dispara_and_consume_kept_apart():
    """A component-triggered call is dispara; a page-load call with no
    component involved is consume - InferredRequest's own triggered_by/
    loaded_by split, never conflated."""
    from core.interfaces import VisitStep

    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("example.com/cart", status="Finished")
    store.record_component("example.com/", "button.buy", tag="button")

    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("example.com/", "button.buy", "click", step=step)
    store.record_component_network(
        "example.com/", "button.buy",
        [{"method": "POST", "host": "example.com", "path": "/api/cart",
          "visit_id": step.visit_id, "step_seq": step.seq}],
    )
    store.record_page_network(
        "example.com/cart",
        [{"method": "GET", "host": "example.com", "path": "/api/inventory"}],
    )

    document = build_export_graph(_request(store))

    ids = {node["id"] for node in document["@graph"] if node["type"] == "Endpoint"}
    assert ids == {"POST example.com/api/cart", "GET example.com/api/inventory"}
    component = _node(document, "example.com/|button.buy")
    assert component["dispara"] == ["POST example.com/api/cart"]
    cart_page = _node(document, "example.com/cart")
    assert cart_page["consume"] == ["GET example.com/api/inventory"]


def test_the_document_carries_run_id_and_a_stable_context_reference():
    document = build_export_graph(_request(_store(), run_id="20260820T010203Z"))

    assert document["@context"] == "./export.context.jsonld"
    assert document["run_id"] == "20260820T010203Z"
    assert "generated_at" in document


def test_reserved_node_types_never_appear_until_their_own_ticket_populates_them():
    """docs/adr/0002's reserved-vs-populated split, enforced: Modulo et al.
    are in the vocabulary, not in this run's @graph. Token is populated
    since ticket #100 (ADR-0005 point 5)."""
    store = _store()
    store.upsert_page("example.com/", status="Finished")

    document = build_export_graph(_request(store))

    types = {node["type"] for node in document["@graph"]}
    assert types <= {"Pantalla", "Componente", "Endpoint", "Token"}


def test_token_nodes_are_keyed_by_their_own_dtcg_path():
    """No short_hash needed - a token's position in the tree (core.color.
    text-1) is already a short, stable identity, unlike a Page/Component/
    Endpoint's."""
    tokens_document = {
        "core": {"color": {"text-1": {"$type": "color", "$value": "#111"}}},
        "semantic": {},
    }

    nodes = _token_nodes(tokens_document)

    assert nodes == {"core.color.text-1": {"id": "core.color.text-1", "type": "Token", "label": "core.color.text-1"}}


def test_token_nodes_recurse_through_nested_groups():
    tokens_document = {
        "core": {"typography": {"type-1": {"$type": "typography", "$value": {"fontSize": "16px"}}}},
        "semantic": {"color": {"brand": {"$type": "color", "$value": "{core.color.text-1}"}}},
    }

    nodes = _token_nodes(tokens_document)

    assert set(nodes) == {"core.typography.type-1", "semantic.color.brand"}


def test_generated_export_document_is_valid_json_ld_and_deterministic():
    import re
    from core import bootstrap  # noqa: F401  (registers the document generators)
    from core.registry import DOCUMENT_REGISTRY

    store = _store()
    store.upsert_page("example.com/", status="Finished", title="Home")

    generator = DOCUMENT_REGISTRY.create("export")
    outputs = generator.outputs(_request(store))

    assert len(outputs) == 1
    assert outputs[0].kind == "source"
    assert outputs[0].extension == "json"
    parsed = json.loads(outputs[0].content)
    assert parsed["@graph"][0]["type"] == "Pantalla"

    strip_timestamp = lambda text: re.sub(r'"generated_at": "[^"]*"', '"generated_at": ""', text)
    again = generator.outputs(_request(store))[0].content
    assert strip_timestamp(outputs[0].content) == strip_timestamp(again)
