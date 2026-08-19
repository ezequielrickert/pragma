"""Regression tests for `pragma docs`'s own entry point
(core/docs_engine.py): proves it reads an already-crawled site's graph
store and generates documents with no crawl, works against a
`static`-only DB (no `cluster`/`dynamic` required), and warns rather
than crashing on an empty site.
"""
from core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
from core.config import PragmaConfig
from core.docs_engine import DocsEngine
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY
from database.ladybug.store import LadybugGraphStore

SITE = "docs.example"


def _seed_static_only_site(graph_store) -> None:
    """A site with only what `pragma static` writes - a page and its
    components, no component families, no semantic tier."""
    graph_store.upsert_page(SITE, status="Finished", components=1, description="Home", title="Home")
    graph_store.record_component(SITE, "cta", tag="button", text="Sign up", component_type="button", facts=None)


def test_docs_engine_generates_documents_from_an_existing_static_only_db(tmp_path):
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site=SITE)
    graph_store.connect()
    _seed_static_only_site(graph_store)

    engine = DocsEngine(
        AGENT_REGISTRY.create("mock"), graph_store, SITE, out_dir=str(tmp_path), documents=["tree"],
    )
    result = engine.run()

    assert result.site == SITE
    names = {d.name for d in result.documents}
    assert names == {"tree", "master"}
    assert result.manifest_path
    assert result.index_path


def test_docs_engine_projects_the_navigation_graph_before_generating(tmp_path):
    """The ticket's own absorbed step: page_metrics (click depth, degree,
    ...) must exist by the time documents are generated, not just by the
    time the run finishes. `project_graph` produces nothing for an
    edge-less input (a valid result, not an error - see its own
    docstring), so this needs at least one recorded edge to prove
    anything.

    A disk-backed store, not `"memory"`: `DocsEngine.run()` closes the
    store when it's done, same as every other engine; reading it back
    afterward has to reconnect, and `"memory"`'s own reconnect opens a
    fresh, empty database (ephemeral by construction) rather than
    finding what was just written.
    """
    graph_store = LadybugGraphStore(SITE, directory=str(tmp_path))
    graph_store.connect()
    _seed_static_only_site(graph_store)
    graph_store.upsert_page(f"{SITE}/about", status="Finished")
    graph_store.record_edge(SITE, f"{SITE}/about", "cta", "click")

    engine = DocsEngine(AGENT_REGISTRY.create("mock"), graph_store, SITE, documents=[])
    engine.run()

    reopened = LadybugGraphStore(SITE, directory=str(tmp_path))
    reopened.connect()
    metrics = reopened.get_page_metrics()
    reopened.close()
    assert any(m["url"] == SITE for m in metrics)


def test_docs_engine_warns_but_does_not_crash_on_an_empty_site(capsys):
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site="empty.example")
    graph_store.connect()

    engine = DocsEngine(AGENT_REGISTRY.create("mock"), graph_store, "empty.example", documents=[])
    result = engine.run()

    assert result.site == "empty.example"
    assert "no pages recorded" in capsys.readouterr().out


def test_docs_engine_from_config_takes_a_bare_site_not_a_url():
    """Reads an existing `pragma static` run already on disk - it never
    derives `site` from a URL the way `Engine`/`StaticEngine` do, since
    there's no URL to parse in the first place. Same convention
    `ClusterEngine.from_config` uses."""
    config = PragmaConfig(agent="mock", graph_store="memory")
    engine = DocsEngine.from_config(config, SITE)

    assert engine.site == SITE
