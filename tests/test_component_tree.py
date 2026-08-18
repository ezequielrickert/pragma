"""Unit tests for generators/component_tree.py - built directly against
LadybugGraphStore in-memory mode, no live crawl needed (build_component_tree/
render_ascii_tree only touch the store's read surface).
"""
from core.interfaces import VisitStep
from generators.component_tree import (
    SiteTree,
    TreeLeaf,
    TreePage,
    build_component_tree,
    generate_component_tree_document,
    group_by_region,
    render_ascii_tree,
)
from database.ladybug.store import LadybugGraphStore

SITE = "tree-test-site"


def _store():
    store = LadybugGraphStore(SITE)
    store.connect()
    return store


def test_build_component_tree_first_level_uses_page_titles():
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home Page")
    tree = build_component_tree(store, SITE)
    assert tree.pages[0].title == "Home Page"


def test_build_component_tree_falls_back_to_url_when_no_title():
    store = _store()
    store.upsert_page("example.com", status="Finished")
    tree = build_component_tree(store, SITE)
    assert tree.pages[0].title == "example.com"


def test_option_redirect_absent_when_no_interaction_carries_a_source_path():
    """An ordinary (non-consolidated) interaction must not spuriously produce
    an option_redirects line."""
    store = _store()
    store.upsert_page("example.com", status="Finished")
    store.record_component_interaction("example.com", "a#about", action="click", resulting_url="")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.option_redirects == []


def test_placeholder_value_from_last_fill_interaction():
    store = _store()
    store.upsert_page("example.com", status="Finished")
    store.record_component_interaction("example.com", "input#email", action="fill", value="test@example.com")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "input#email")
    assert leaf.placeholder_value == "test@example.com"


def test_redirect_target_resolves_to_first_level_page_reference():
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.upsert_page("example.com/about", status="Finished", title="About Us")
    store.record_component_interaction("example.com", "a#about", action="click", resulting_url="example.com/about")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.redirect_target == '"About Us" (example.com/about)'


def test_redirect_target_falls_back_to_edges_when_component_interaction_missing_resulting_url():
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.upsert_page("example.com/about", status="Finished", title="About Us")
    # Component recorded (interacted, but its own interaction row carries no
    # resulting_url) - only the separate graph edge has the destination.
    store.record_component_interaction("example.com", "a#about", action="click", resulting_url="")
    store.record_edge("example.com", "example.com/about", component="a#about", action="click")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.redirect_target == '"About Us" (example.com/about)'


def test_choice_group_variants_and_option_redirects_render_from_real_options():
    """The fact a per-option Component node used to carry on its own now
    lives on the group's single node - see _build_option_redirects."""
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.upsert_page("example.com/checkout", status="Finished", title="Checkout")
    store.record_component("example.com", "div#ship", tag="div")
    store.record_component_options(
        "example.com", "div#ship",
        {"group": "ship_method", "options": [
            {"path": "input#pickup", "text": "Pickup", "selected": False},
            {"path": "input#delivery", "text": "Home delivery", "selected": True},
        ]},
    )
    store.record_component_interaction(
        "example.com", "div#ship", action="click", resulting_url="example.com/checkout",
        source_path="input#delivery",
    )

    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "div#ship")

    assert leaf.variants == ["Pickup", "Home delivery (selected)"]
    assert leaf.option_redirects == ['"Home delivery" -> "Checkout" (example.com/checkout)']


def test_stepper_variant_reports_its_current_value():
    store = _store()
    store.upsert_page("example.com", status="Finished")
    store.record_component("example.com", "div#qty", tag="div")
    store.record_component_options(
        "example.com", "div#qty",
        {"increment_path": "button#plus", "decrement_path": "button#minus",
         "value_path": "span#qty-value", "current_value": "3"},
    )

    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "div#qty")

    assert leaf.variants == ["stepper (current value: 3)"]


def test_network_request_line_reports_method_path_and_outcome():
    store = _store()
    store.upsert_page("example.com", status="Finished")
    store.record_component("example.com", "button#pay", tag="button")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("example.com", "button#pay", "click", step=step)
    store.record_component_network(
        "example.com", "button#pay",
        [{
            "method": "POST", "host": "example.com", "path": "/api/pay", "query_params": [],
            "resource_type": "fetch", "status": 422, "status_text": "", "failed": False,
            "failure_text": None, "body_shape": "", "response_shape": "",
            "request_body_excerpt": "", "request_body_length": 0, "request_body_hash": "",
            "response_body_excerpt": "", "response_body_length": 0, "response_body_hash": "",
            "latency_ms": None, "media_type": "", "auth_scheme": "",
            "visit_id": "v1", "step_seq": 1, "is_first_party": True,
        }],
    )

    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "button#pay")

    assert leaf.requests == ["POST /api/pay -> 422"]


def test_text_content_appears_as_distinct_leaf_kind():
    store = _store()
    store.upsert_page("example.com", status="Finished")
    store.record_text_content("example.com", "body > h1", tag="h1", text="Welcome")
    tree = build_component_tree(store, SITE)
    leaf = tree.pages[0].leaves[0]
    assert leaf.kind == "text"
    assert leaf.label == "h1"
    assert leaf.text == "Welcome"


def test_render_ascii_tree_is_deterministic():
    tree = SiteTree(site="example.com", pages=[
        TreePage(url="example.com", title="Home", leaves=[
            TreeLeaf(kind="component", path="a", label="button", text="Click me"),
        ]),
    ])
    assert render_ascii_tree(tree) == render_ascii_tree(tree)


def test_render_ascii_tree_box_drawing_vs_ascii_modes():
    tree = SiteTree(site="example.com", pages=[
        TreePage(url="example.com", title="Home", leaves=[
            TreeLeaf(kind="component", path="a", label="button", text="Click me"),
        ]),
    ])
    box = render_ascii_tree(tree, use_box_drawing=True)
    ascii_only = render_ascii_tree(tree, use_box_drawing=False)
    assert box != ascii_only
    assert "├──" in box or "└──" in box
    assert "|--" in ascii_only or "`--" in ascii_only
    assert "├" not in ascii_only and "└" not in ascii_only


def test_generate_component_tree_document_includes_header_and_body():
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.record_component("example.com", "button#a", tag="button", text="Click me")
    doc = generate_component_tree_document(store, SITE)
    assert f"# Component Tree: {SITE}" in doc
    assert "1 pages, 1 components, 0 text blocks" in doc
    assert "Home (example.com)" in doc
    assert "Click me" in doc


# --- landmark regions ---

def _store_with_regions():
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.record_components("example.com", [
        {"path": "a#about", "tag": "a", "text": "About"},
        {"path": "button#buy", "tag": "button", "text": "Buy"},
    ])
    store.record_component_ancestors("example.com", [
        {"path": "a#about", "ancestors": [
            {"path": "nav", "tag": "nav", "role": "", "landmark": "navigation", "id": "", "class": ""},
        ]},
        {"path": "button#buy", "ancestors": [
            {"path": "main", "tag": "main", "role": "", "landmark": "main", "id": "", "class": ""},
        ]},
    ])
    return store


def test_a_leaf_carries_the_landmark_region_it_sits_in():
    tree = build_component_tree(_store_with_regions(), SITE)

    by_path = {leaf.path: leaf.region for leaf in tree.pages[0].leaves}
    assert by_path["a#about"] == "navigation"
    assert by_path["button#buy"] == "main"


def test_the_rendered_tree_nests_leaves_under_their_region():
    rendered = render_ascii_tree(build_component_tree(_store_with_regions(), SITE))

    assert "<navigation>" in rendered
    assert "<main>" in rendered


def test_a_page_with_no_recorded_region_renders_flat_as_before():
    """No region header, no extra indent level - the pre-containment shape."""
    store = _store()
    store.upsert_page("example.com", status="Finished", title="Home")
    store.record_components("example.com", [{"path": "a#about", "tag": "a", "text": "About"}])

    rendered = render_ascii_tree(build_component_tree(store, SITE))

    assert "(no landmark region)" not in rendered
    assert "<" not in rendered.split("Home (example.com)")[1]


def test_leaves_outside_any_region_are_grouped_last():
    """A page that has both kinds keeps the unnamed group at the bottom, so
    the named regions read first."""
    store = _store_with_regions()
    store.record_components("example.com", [{"path": "span#note", "tag": "span", "text": "Note"}])

    groups = group_by_region(build_component_tree(store, SITE).pages[0].leaves)

    assert [region for region, _ in groups] == ["main", "navigation", ""]
