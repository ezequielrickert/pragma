"""Regression tests for `pragma cluster`'s own entry point
(core/cluster_engine.py) - proves it reads an already-crawled site's
components, writes families back, and touches nothing else (no crawling,
no document generation).
"""
from core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
from core.cluster_engine import ClusterEngine
from core.config import PragmaConfig
from core.interfaces import ComponentFacts
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY

SITE = "shop.example"


def _seed_two_button_variants(graph_store) -> None:
    """Two buttons similar enough to family together but not identical -
    distinct `href` keeps them two rows rather than one content-hash-
    collapsed row (issue #134), which is what a *family* (several
    distinct-but-similar components) actually needs to test, as opposed
    to exact-tier collapse (issue #139) folding two truly identical ones
    into a single canonical row."""
    graph_store.record_component(
        "shop.example/", "btn1", tag="button", text="Add to cart",
        component_type="submit button", facts=ComponentFacts(css_class="btn btn-primary", href="/cart/add"),
    )
    graph_store.record_component(
        "shop.example/", "btn2", tag="button", text="Buy now",
        component_type="submit button", facts=ComponentFacts(css_class="btn btn-secondary", href="/checkout"),
    )


def test_cluster_engine_groups_components_already_in_the_graph_store():
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site=SITE)
    graph_store.connect()
    _seed_two_button_variants(graph_store)

    engine = ClusterEngine(AGENT_REGISTRY.create("mock"), graph_store, SITE)
    result = engine.run()

    assert result.site == SITE
    assert result.families == 1


def test_cluster_engine_warns_but_does_not_crash_on_an_empty_site(capsys):
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site="empty.example")
    graph_store.connect()

    engine = ClusterEngine(AGENT_REGISTRY.create("mock"), graph_store, "empty.example")
    result = engine.run()

    assert result.families == 0
    assert "no components recorded" in capsys.readouterr().out


def test_cluster_engine_from_config_takes_a_bare_site_not_a_url():
    """Clustering resumes against a `pragma static` run already on disk -
    it never derives `site` from `config.url` the way `Engine`/
    `StaticEngine` do, since there is no URL to parse in the first place."""
    config = PragmaConfig(agent="mock", graph_store="memory")
    engine = ClusterEngine.from_config(config, SITE)

    assert engine.site == SITE
