"""Unit tests for generators/graph_export.py - built directly against
LadybugGraphStore in-memory mode, same convention as
tests/test_document_pipeline.py (build_export_graph only touches the
store's read surface)."""
import json

from core.documents import DocumentRequest
from database.ladybug.store import LadybugGraphStore
from generators.component_catalog import CatalogEntry, CatalogVariant
from generators.graph_export import (
    _build_location_index,
    _entidad_nodes,
    _modulo_nodes,
    _populate_usa_token,
    _requisito_nodes,
    _token_nodes,
    build_export_graph,
)

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
    assert len(page["contiene"]) == 1
    component = _node(document, page["contiene"][0])
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
    page = _node(document, "example.com/")
    component = _node(document, page["contiene"][0])
    assert "navega_a" not in component


def test_navigation_via_a_component_attributes_the_edge_to_it():
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("example.com/about", status="Finished")
    store.record_component("example.com/", "a.about", tag="a")
    store.record_edge("example.com/", "example.com/about", component="a.about", action="click")

    document = build_export_graph(_request(store))

    page = _node(document, "example.com/")
    component = _node(document, page["contiene"][0])
    assert component["navega_a"] == ["example.com/about"]
    assert "navega_a" not in page


def test_a_component_reused_across_pages_is_one_shared_componente_node():
    """Byte-identical content collapses onto one canonical Component row
    (issue #136's write-time MERGE) - the export reflects that as one
    shared Componente node, contiene'd by both pages, not two separate
    ones (issue #141)."""
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.upsert_page("example.com/about", status="Finished")
    store.record_component("example.com/", "a.nav", tag="a", text="Home")
    store.record_component("example.com/about", "a.nav2", tag="a", text="Home")

    document = build_export_graph(_request(store))

    componente_ids = {node["id"] for node in document["@graph"] if node["type"] == "Componente"}
    assert len(componente_ids) == 1
    componente_id = next(iter(componente_ids))
    assert _node(document, "example.com/")["contiene"] == [componente_id]
    assert _node(document, "example.com/about")["contiene"] == [componente_id]


def test_build_location_index_maps_every_ledger_entry_to_its_component_id():
    store = _store()
    store.upsert_page("example.com/", status="Finished")
    store.record_component("example.com/", "a.about", tag="a", text="About")

    ledger = store.get_component_ledger()
    index = _build_location_index(ledger)

    assert index[("example.com/", "a.about")] == ledger["example.com/"]["a.about"]["id"]


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
    page = _node(document, "example.com/")
    component = _node(document, page["contiene"][0])
    assert component["dispara"] == ["POST example.com/api/cart"]
    cart_page = _node(document, "example.com/cart")
    assert cart_page["consume"] == ["GET example.com/api/inventory"]


def test_the_document_carries_run_id_and_a_stable_context_reference():
    document = build_export_graph(_request(_store(), run_id="20260820T010203Z"))

    assert document["@context"] == "./export.context.jsonld"
    assert document["run_id"] == "20260820T010203Z"
    assert "generated_at" in document


def test_reserved_node_types_never_appear_until_their_own_ticket_populates_them():
    """docs/adr/0002's reserved-vs-populated split, enforced: Escenario et
    al. are in the vocabulary, not in this run's @graph. Token is
    populated since ticket #100 (ADR-0005 point 5); Modulo since ticket
    #102 (ADR-0007); Entidad since ticket #103 (ADR-0008 point 5);
    Requisito since ticket #104 (ADR-0009 point 5)."""
    store = _store()
    store.upsert_page("example.com/", status="Finished")

    document = build_export_graph(_request(store))

    types = {node["type"] for node in document["@graph"]}
    assert types <= {"Pantalla", "Componente", "Endpoint", "Token", "Modulo", "Entidad", "Requisito"}


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


def test_modulo_nodes_contain_their_member_pantallas():
    pantallas = {
        "example.com/admin/a": {"id": "example.com/admin/a", "type": "Pantalla"},
        "example.com/admin/b": {"id": "example.com/admin/b", "type": "Pantalla"},
    }

    modulos = _modulo_nodes(pantallas, root=None)

    assert modulos["MOD-admin"]["contiene"] == ["example.com/admin/a", "example.com/admin/b"]
    assert modulos["MOD-admin"]["type"] == "Modulo"


def test_no_pantallas_means_no_modulo_nodes():
    assert _modulo_nodes({}, root=None) == {}


def test_entidad_nodes_and_depende_de_edge_from_a_citing_endpoint():
    endpoints = {"POST api.example.com/checkout": {"id": "POST api.example.com/checkout", "type": "Endpoint"}}
    data_model_document = {
        "entities": {
            "checkout": {
                "description": "", "fields": {
                    "email": {"observed_in": {"api_endpoints": ["POST api.example.com/checkout"]}},
                },
            },
        },
    }

    entidades = _entidad_nodes(data_model_document, endpoints)

    assert entidades["checkout"]["type"] == "Entidad"
    assert endpoints["POST api.example.com/checkout"]["depende_de"] == ["checkout"]


def test_entidad_nodes_with_no_citing_endpoint_is_still_a_node():
    data_model_document = {"entities": {"checkout": {"description": "", "fields": {}}}}

    entidades = _entidad_nodes(data_model_document, endpoints={})

    assert "checkout" in entidades


def test_requisito_nodes_and_implementa_from_a_citing_pantalla_and_endpoint():
    pantallas = {"example.com/": {"id": "example.com/", "type": "Pantalla"}}
    endpoints = {"POST api.example.com/checkout": {"id": "POST api.example.com/checkout", "type": "Endpoint"}}
    requirements_document = {"requirements": [{
        "id": "REQ-abc", "syntax_text": "WHEN..., THE SYSTEM SHALL...",
        "links": {
            "screens": ["SCR-880970443b"],  # short_hash("example.com/")
            "endpoints": ["POST api.example.com/checkout"], "data_entities": [], "depends_on": [],
        },
    }]}

    requisitos = _requisito_nodes(requirements_document, pantallas, endpoints, entidades={})

    assert requisitos["REQ-abc"]["type"] == "Requisito"
    assert pantallas["example.com/"]["implementa"] == ["REQ-abc"]
    assert endpoints["POST api.example.com/checkout"]["implementa"] == ["REQ-abc"]


def test_requisito_cubre_a_cited_entidad():
    requirements_document = {"requirements": [{
        "id": "REQ-abc", "syntax_text": "...",
        "links": {"screens": [], "endpoints": [], "data_entities": ["checkout"], "depends_on": []},
    }]}

    requisitos = _requisito_nodes(requirements_document, pantallas={}, endpoints={}, entidades={"checkout": {}})

    assert requisitos["REQ-abc"]["cubre"] == ["checkout"]


def test_a_citation_with_no_matching_node_is_silently_skipped():
    requirements_document = {"requirements": [{
        "id": "REQ-abc", "syntax_text": "...",
        "links": {"screens": ["SCR-unknown"], "endpoints": [], "data_entities": [], "depends_on": []},
    }]}

    requisitos = _requisito_nodes(requirements_document, pantallas={}, endpoints={}, entidades={})

    assert "REQ-abc" in requisitos


def _catalog_entry(member_paths, variants=()):
    return CatalogEntry(
        name="Button", tag="button", component_type="button", purpose="",
        atomic_level="atom", member_count=len(member_paths),
        used_on=tuple(sorted({page_url for page_url, _ in member_paths})),
        props=(), variants=variants, states_observed=(), member_paths=member_paths,
    )


def test_usa_token_edges_one_per_real_component_instance():
    """A pattern used twice on the same page gets two edges, one per
    member_paths entry - not one edge per pattern (used_on would collapse
    both instances into a single page)."""
    componentes = {
        "comp-buy": {"id": "comp-buy", "type": "Componente"},
        "comp-checkout": {"id": "comp-checkout", "type": "Componente"},
    }
    location_to_id = {("shop/", "button.buy"): "comp-buy", ("shop/", "button.checkout"): "comp-checkout"}
    tokens_document = {"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}
    entry = _catalog_entry(
        member_paths=(("shop/", "button.buy"), ("shop/", "button.checkout")),
        variants=(CatalogVariant(modifiers=(), background_color="rgb(45, 119, 55)", count=2, example_text=""),),
    )

    _populate_usa_token(componentes, [entry], tokens_document, location_to_id)

    assert componentes["comp-buy"]["usa_token"] == ["core.color.surface-1"]
    assert componentes["comp-checkout"]["usa_token"] == ["core.color.surface-1"]


def test_usa_token_stays_absent_when_no_variant_matches_a_color_token():
    componentes = {"comp-buy": {"id": "comp-buy", "type": "Componente"}}
    location_to_id = {("shop/", "button.buy"): "comp-buy"}
    tokens_document = {"core": {"color": {}}, "semantic": {}}
    entry = _catalog_entry(member_paths=(("shop/", "button.buy"),))

    _populate_usa_token(componentes, [entry], tokens_document, location_to_id)

    assert "usa_token" not in componentes["comp-buy"]


def test_usa_token_edge_lands_once_even_when_two_locations_share_a_reused_component():
    """Two `member_paths` entries that resolve to the same reused
    Componente (issue #141) still produce one edge on it, via
    `_add_edge`'s own dedup - not two identical entries."""
    componentes = {"comp-nav": {"id": "comp-nav", "type": "Componente"}}
    location_to_id = {("shop/", "a.nav"): "comp-nav", ("shop/about", "a.nav2"): "comp-nav"}
    tokens_document = {"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}
    entry = _catalog_entry(
        member_paths=(("shop/", "a.nav"), ("shop/about", "a.nav2")),
        variants=(CatalogVariant(modifiers=(), background_color="rgb(45, 119, 55)", count=2, example_text=""),),
    )

    _populate_usa_token(componentes, [entry], tokens_document, location_to_id)

    assert componentes["comp-nav"]["usa_token"] == ["core.color.surface-1"]


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
