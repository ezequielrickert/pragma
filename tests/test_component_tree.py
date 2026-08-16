"""Unit tests for generators/component_tree.py - built directly against
InMemoryGraphStore, no live crawl needed (build_component_tree/render_ascii_tree
only touch GraphStore's read surface)."""
from generators.component_tree import (
    SiteTree,
    TreeLeaf,
    TreePage,
    build_component_tree,
    generate_component_tree_document,
    render_ascii_tree,
)
from database.memory_graph_store import InMemoryGraphStore

SITE = "tree-test-site"


def _store():
    store = InMemoryGraphStore()
    store.connect()
    return store


def test_build_component_tree_first_level_uses_page_titles():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished", title="Home Page")
    tree = build_component_tree(store, SITE)
    assert tree.pages[0].title == "Home Page"


def test_build_component_tree_falls_back_to_url_when_no_title():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    tree = build_component_tree(store, SITE)
    assert tree.pages[0].title == "example.com"


def test_stepper_variant_renders():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component(SITE, "example.com", "button#plus", tag="button", text="+")
    store.record_component_options(
        SITE, "example.com", "button#plus",
        {"container": "div", "increment_path": "button#plus", "decrement_path": "button#minus", "current_value": "3"},
    )
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "button#plus")
    assert leaf.variants == ["stepper (current value: 3)"]


def test_choice_group_variant_renders():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component(SITE, "example.com", "input#s", tag="input")
    store.record_component_options(
        SITE, "example.com", "input#s",
        {"group": "size", "options": [{"text": "Small", "selected": True}, {"text": "Large", "selected": False}]},
    )
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "input#s")
    assert leaf.variants == ["Small (selected)", "Large"]


def test_revealed_options_variant_renders():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component(SITE, "example.com", "button#trigger", tag="button")
    store.record_component_options(
        SITE, "example.com", "button#trigger",
        {"trigger": "button#trigger", "revealed_options": [{"text": "A", "selected": False}, {"text": "B", "selected": False}]},
    )
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "button#trigger")
    assert leaf.variants == ["A", "B"]


def test_option_redirect_renders_under_the_consolidated_choice_group_leaf():
    """A dropdown/choice-group option that navigated somewhere different from
    its siblings still shows up - as a line under the group's single leaf,
    tagged with which choice caused it, not as its own leaf."""
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished", title="Home")
    store.upsert_page(SITE, "example.com/large-details", status="Finished", title="Large Details")
    store.record_component(SITE, "example.com", "div#opt-small", tag="div", text="Small")
    store.record_component_options(
        SITE, "example.com", "div#opt-small",
        {
            "group": "div#sizeList",
            "options": [
                {"path": "div#opt-small", "text": "Small", "selected": False},
                {"path": "div#opt-large", "text": "Large", "selected": False},
            ],
        },
    )
    store.record_component_interaction(
        SITE, "example.com", "div#opt-small", action="click",
        resulting_url="example.com/large-details", source_path="div#opt-large",
    )

    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "div#opt-small")
    assert leaf.option_redirects == ['"Large" -> "Large Details" (example.com/large-details)']

    rendered = render_ascii_tree(tree)
    assert '"Large" -> "Large Details"' in rendered


def test_option_redirect_absent_when_no_interaction_carries_a_source_path():
    """An ordinary (non-consolidated) interaction must not spuriously produce
    an option_redirects line."""
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component_interaction(SITE, "example.com", "a#about", action="click", resulting_url="")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.option_redirects == []


def test_placeholder_value_from_last_fill_interaction():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component_interaction(SITE, "example.com", "input#email", action="fill", value="test@example.com")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "input#email")
    assert leaf.placeholder_value == "test@example.com"


def test_redirect_target_resolves_to_first_level_page_reference():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished", title="Home")
    store.upsert_page(SITE, "example.com/about", status="Finished", title="About Us")
    store.record_component_interaction(SITE, "example.com", "a#about", action="click", resulting_url="example.com/about")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.redirect_target == '"About Us" (example.com/about)'


def test_redirect_target_falls_back_to_edges_when_component_interaction_missing_resulting_url():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished", title="Home")
    store.upsert_page(SITE, "example.com/about", status="Finished", title="About Us")
    # Component recorded (interacted, but its own interaction row carries no
    # resulting_url) - only the separate graph edge has the destination.
    store.record_component_interaction(SITE, "example.com", "a#about", action="click", resulting_url="")
    store.record_edge(SITE, "example.com", "example.com/about", component="a#about", action="click")
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "a#about")
    assert leaf.redirect_target == '"About Us" (example.com/about)'


def test_network_requests_render_as_lines():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_component_network(
        SITE, "example.com", "button#ping",
        [{"method": "GET", "url": "/api/ping", "resource_type": "fetch", "status": 200, "failed": False, "failure_text": None}],
    )
    tree = build_component_tree(store, SITE)
    leaf = next(l for l in tree.pages[0].leaves if l.path == "button#ping")
    assert leaf.requests == ["GET /api/ping -> 200"]


def test_text_content_appears_as_distinct_leaf_kind():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.record_text_content(SITE, "example.com", "body > h1", tag="h1", text="Welcome")
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
    store.upsert_page(SITE, "example.com", status="Finished", title="Home")
    store.record_component(SITE, "example.com", "button#a", tag="button", text="Click me")
    doc = generate_component_tree_document(store, SITE)
    assert f"# Component Tree: {SITE}" in doc
    assert "1 pages, 1 components, 0 text blocks" in doc
    assert "Home (example.com)" in doc
    assert "Click me" in doc
