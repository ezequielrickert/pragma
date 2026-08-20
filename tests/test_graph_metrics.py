"""Unit tests for core/graph_metrics.py - pure functions over an
@graph-shaped node list, the same shape generators/graph_export.py
assembles. No store, no model."""
from core.graph_metrics import compute_graph_metrics


def _pantalla(node_id, **edges):
    return {"id": node_id, "type": "Pantalla", **edges}


def test_two_pages_sharing_a_first_segment_form_a_path_prefix_module():
    graph = [
        _pantalla("example.com/admin/users"),
        _pantalla("example.com/admin/settings"),
    ]

    metrics = compute_graph_metrics(graph)

    assert {m.module_id for m in metrics.node_modules} == {"MOD-admin"}
    assert all(m.module_label == "Admin" for m in metrics.node_modules)


def test_a_single_page_with_a_unique_segment_is_not_a_prefix_cluster():
    """One page with a path of its own isn't evidence of a real module -
    it falls through to Leiden instead of becoming a module of one."""
    graph = [
        _pantalla("example.com/admin/users"),
        _pantalla("example.com/admin/settings"),
        _pantalla("example.com/lonely", navega_a=["example.com/admin/users"]),
    ]

    metrics = compute_graph_metrics(graph)

    lonely_module = next(m for m in metrics.node_modules if m.node_id == "example.com/lonely")
    assert lonely_module.module_id != "MOD-lonely"


def test_leiden_modules_are_deterministic_across_two_runs():
    graph = [
        _pantalla("a/1", navega_a=["a/2"]), _pantalla("a/2", navega_a=["a/1"]),
        _pantalla("a/3", navega_a=["a/4"]), _pantalla("a/4", navega_a=["a/3"]),
    ]

    first = compute_graph_metrics(graph).node_modules
    second = compute_graph_metrics(graph).node_modules

    assert first == second


def test_a_leiden_module_id_is_a_hash_not_a_readable_slug():
    graph = [_pantalla("a/1", navega_a=["a/2"]), _pantalla("a/2", navega_a=["a/1"])]

    metrics = compute_graph_metrics(graph)

    assert all(m.module_id.startswith("MOD-") and m.module_label == "" for m in metrics.node_modules)


def test_depth_is_bfs_hops_from_the_given_root():
    graph = [
        _pantalla("example.com/", navega_a=["example.com/a"]),
        _pantalla("example.com/a", navega_a=["example.com/b"]),
        _pantalla("example.com/b"),
    ]

    metrics = compute_graph_metrics(graph, root="example.com/")

    by_id = {m.node_id: m.depth for m in metrics.node_metrics}
    assert by_id == {"example.com/": 0, "example.com/a": 1, "example.com/b": 2}


def test_depth_is_none_for_a_page_the_root_cannot_reach():
    graph = [_pantalla("example.com/", navega_a=["example.com/a"]), _pantalla("example.com/isolated")]

    metrics = compute_graph_metrics(graph, root="example.com/")

    isolated = next(m for m in metrics.node_metrics if m.node_id == "example.com/isolated")
    assert isolated.depth is None


def test_depth_is_none_everywhere_without_a_root():
    graph = [_pantalla("example.com/", navega_a=["example.com/a"]), _pantalla("example.com/a")]

    metrics = compute_graph_metrics(graph)

    assert all(m.depth is None for m in metrics.node_metrics)


def test_a_high_betweenness_high_in_degree_node_is_a_bottleneck():
    """A hub every spoke must pass through: high betweenness, in_degree>=3."""
    # A bidirectional star: every spoke reaches every other spoke only
    # through the hub, so the hub genuinely sits on the shortest path
    # between them - real betweenness, not just a high in_degree.
    hub_targets = [f"example.com/spoke{i}" for i in range(4)]
    graph = [_pantalla("example.com/hub", navega_a=hub_targets)]
    graph += [_pantalla(spoke, navega_a=["example.com/hub"]) for spoke in hub_targets]

    metrics = compute_graph_metrics(graph)

    hub = next(m for m in metrics.node_metrics if m.node_id == "example.com/hub")
    assert hub.in_degree >= 3
    assert hub.is_bottleneck is True


def test_a_zero_betweenness_node_is_never_a_bottleneck_even_at_the_percentile_floor():
    """A graph with no real internal betweenness (everything is a leaf)
    must not call every well-linked node a bottleneck just because 0.0
    happens to be the 90th percentile too."""
    graph = [_pantalla(f"example.com/{i}") for i in range(5)]

    metrics = compute_graph_metrics(graph)

    assert all(m.is_bottleneck is False for m in metrics.node_metrics)


def test_component_and_endpoint_nodes_are_never_assigned_a_module():
    """Module derivation is screen-scoped (ADR-0007's own SCR-root/
    screen-depth framing) - a Componente or Endpoint node never gets a
    module_id of its own."""
    graph = [
        _pantalla("example.com/admin/a"), _pantalla("example.com/admin/b"),
        {"id": "example.com/admin/a|button", "type": "Componente"},
        {"id": "GET example.com/api", "type": "Endpoint"},
    ]

    metrics = compute_graph_metrics(graph)

    assert {m.node_id for m in metrics.node_modules} == {"example.com/admin/a", "example.com/admin/b"}


def test_an_empty_graph_produces_no_metrics_or_modules():
    metrics = compute_graph_metrics([])

    assert metrics.node_metrics == ()
    assert metrics.node_modules == ()
