"""Tests for analysis/graph_projection.py - pure function, hand-built edge
lists, no GraphStore/browser dependency (same convention
tests/test_network_filter.py and tests/test_redaction.py already use)."""
from analysis.graph_projection import project_graph


def _edge(from_url, to_url, component="link", action="GOTO"):
    return {"from": from_url, "to": to_url, "component": component, "action": action}


def test_empty_input_returns_empty_result():
    result = project_graph([])
    assert result.metrics == ()
    assert result.modules == ()
    assert result.cycles == ()


def test_degree_counts_reflect_actual_in_and_out_edges():
    edges = [_edge("home", "about"), _edge("home", "contact"), _edge("about", "home")]
    result = project_graph(edges)

    by_url = {m.url: m for m in result.metrics}
    assert by_url["home"].out_degree == 2
    assert by_url["home"].in_degree == 1
    assert by_url["about"].out_degree == 1
    assert by_url["contact"].out_degree == 0


def test_click_depth_is_shortest_hops_from_root():
    edges = [_edge("home", "about"), _edge("about", "team"), _edge("home", "contact")]
    result = project_graph(edges, root="home")

    by_url = {m.url: m for m in result.metrics}
    assert by_url["home"].click_depth == 0
    assert by_url["about"].click_depth == 1
    assert by_url["contact"].click_depth == 1
    assert by_url["team"].click_depth == 2


def test_click_depth_is_none_without_a_root():
    edges = [_edge("home", "about")]
    result = project_graph(edges, root=None)

    assert all(m.click_depth is None for m in result.metrics)


def test_click_depth_is_none_for_a_page_the_root_cannot_reach():
    """An orphan page - never linked from the root, e.g. discovered only
    via an external referrer - must not silently report depth 0 or crash."""
    edges = [_edge("home", "about"), _edge("orphan-a", "orphan-b")]
    result = project_graph(edges, root="home")

    by_url = {m.url: m for m in result.metrics}
    assert by_url["orphan-a"].click_depth is None
    assert by_url["orphan-b"].click_depth is None


def test_a_navigation_cycle_is_detected():
    """The wiki's own documented incident: a component that clicks back
    into a page it already visited (austral.edu.ar's book-viewer) is
    exactly a graph cycle."""
    edges = [_edge("page-a", "page-b"), _edge("page-b", "page-c"), _edge("page-c", "page-a")]
    result = project_graph(edges)

    assert len(result.cycles) == 1
    assert set(result.cycles[0]) == {"page-a", "page-b", "page-c"}


def test_no_cycle_reported_for_a_pure_tree():
    edges = [_edge("home", "about"), _edge("home", "contact"), _edge("about", "team")]
    assert project_graph(edges).cycles == ()


def test_self_loop_is_a_length_one_cycle():
    """Standard graph theory (and networkx's own documented behavior): a
    self-loop is a cycle of length 1. In practice `GraphStore.get_edges`
    never actually contains one - `GraphStoreSink.record_navigation_edge`
    is only ever called when an interaction's resulting URL differs from
    the page it ran on - but `project_graph` takes plain edge dicts, not a
    guarantee about their source, so it follows networkx's real semantics
    rather than inventing a special case for input its actual producer
    never generates."""
    edges = [_edge("home", "home", action="reveal")]
    assert project_graph(edges).cycles == (("home",),)


def test_articulation_point_identifies_the_only_bridge_between_two_clusters():
    """Two otherwise-separate clusters joined only through one page - remove
    it and the site splits in two, exactly what a real "single point of
    failure in the navigation" finding looks like."""
    edges = [
        _edge("home", "bridge"), _edge("bridge", "home"),
        _edge("bridge", "hub-a"), _edge("hub-a", "bridge"),
        _edge("hub-a", "leaf-a1"), _edge("leaf-a1", "hub-a"),
        _edge("bridge", "hub-b"), _edge("hub-b", "bridge"),
        _edge("hub-b", "leaf-b1"), _edge("leaf-b1", "hub-b"),
    ]
    result = project_graph(edges)

    by_url = {m.url: m for m in result.metrics}
    assert by_url["bridge"].is_articulation_point is True
    assert by_url["home"].is_articulation_point is False
    assert by_url["leaf-a1"].is_articulation_point is False


def test_modules_group_two_disjoint_clusters_separately():
    """Two densely-linked clusters connected by exactly one thin edge -
    Louvain should keep them apart, the whole point of module detection."""
    edges = [
        _edge("shop/home", "shop/catalog"), _edge("shop/catalog", "shop/cart"),
        _edge("shop/cart", "shop/home"), _edge("shop/home", "shop/cart"),
        _edge("blog/home", "blog/post-1"), _edge("blog/post-1", "blog/post-2"),
        _edge("blog/post-2", "blog/home"), _edge("blog/home", "blog/post-2"),
        # The one thin bridge between the two clusters.
        _edge("shop/home", "blog/home"),
    ]
    result = project_graph(edges)

    by_url = {m.url: m.module_id for m in result.modules}
    shop_modules = {by_url[u] for u in ("shop/home", "shop/catalog", "shop/cart")}
    blog_modules = {by_url[u] for u in ("blog/home", "blog/post-1", "blog/post-2")}
    assert len(shop_modules) == 1
    assert len(blog_modules) == 1
    assert shop_modules != blog_modules


def test_module_label_derives_from_shared_url_path_prefix():
    edges = [
        _edge("site.com/investigacion/proyectos", "site.com/investigacion/equipo"),
        _edge("site.com/investigacion/equipo", "site.com/investigacion/proyectos"),
    ]
    result = project_graph(edges)

    labels = {m.module_label for m in result.modules}
    assert labels == {"Investigacion"}


def test_module_label_falls_back_when_members_share_no_path_prefix():
    edges = [_edge("site.com/a", "other.com/b"), _edge("other.com/b", "site.com/a")]
    result = project_graph(edges)

    assert all(m.module_label for m in result.modules)  # never blank


def test_a_page_with_no_edges_at_all_still_gets_its_own_module():
    """Every node in the graph, not just ones with edges connecting them to
    others, ends up in exactly one module - an isolated page is its own
    module of one, not silently dropped."""
    edges = [_edge("isolated", "isolated")]  # self-loop: the only way a lone node has an edge at all
    result = project_graph(edges)

    assert len(result.modules) == 1
    assert result.modules[0].url == "isolated"


def test_pagerank_and_betweenness_are_computed_for_every_page():
    edges = [_edge("home", "about"), _edge("about", "contact"), _edge("contact", "home")]
    result = project_graph(edges)

    assert all(0.0 <= m.pagerank <= 1.0 for m in result.metrics)
    assert all(m.betweenness >= 0.0 for m in result.metrics)
    # A page on every path between the other two should score higher.
    by_url = {m.url: m for m in result.metrics}
    assert by_url["about"].betweenness >= by_url["home"].betweenness
