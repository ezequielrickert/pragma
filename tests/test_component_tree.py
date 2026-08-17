"""Unit tests for generators/component_tree.py - built directly against
LadybugGraphStore in-memory mode, no live crawl needed (build_component_tree/
render_ascii_tree only touch the store's read surface).

Option/Request-derived rendering (stepper/choice-group/revealed-options
variants, option redirects, network-request lines) is untestable here for
now: `record_component_options`/`record_component_network` are
`database/ladybug/deferred.py` no-op placeholders until storage-migration
plan steps 7-8 land. `describe_options("")` (what an absent `options`
field reads back as) returns `None`, so the affected code paths degrade
to "no variants" rather than crashing - covered by
tests/test_ladybug_observation.py's own coverage of the deferred stubs,
not re-tested here.
"""
from generators.component_tree import (
    SiteTree,
    TreeLeaf,
    TreePage,
    build_component_tree,
    generate_component_tree_document,
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
