"""Real end-to-end check for dashboard/graph_assets.py's own `?family=`
URL param (ticket #176, map #172): the landing page's KPI tiles link to
`graph.html?family=<Type>`, and the Graph page has to actually honor it -
opening pre-filtered to that family instead of the ordinary structural
(Pantalla+Modulo) default.

Runs a real Playwright browser against a real export.json (built the
same way tests/test_graph_renderer.py does - a real LadybugGraphStore,
generators/graph_export.py's own real functions), the same "real
fixture, not hand-typed" convention every renderer test in this package
already follows. Opening the file directly (`file://`) rather than
serving it, matching how a reviewer actually opens this page - the CDN
script still loads over a real network fetch."""
import json

from playwright.sync_api import sync_playwright

from core.documents import DocumentRequest
from core.interfaces import Agent
from dashboard.graph_renderer import render_graph_page
from database.ladybug.store import LadybugGraphStore
from generators.graph_export import build_export_graph

SITE = "shop.example"


class StubAgent(Agent):
    def generate(self, prompt, system_instruction=None):
        return "STUB"


def _real_graph_page(tmp_path):
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page(f"{SITE}/", status="Finished", title="Home")
    store.upsert_page(f"{SITE}/about", status="Finished", title="About")
    store.record_component(f"{SITE}/", "a.about", tag="a", text="About")
    store.record_component(f"{SITE}/", "button.buy", tag="button", text="Buy now")
    request = DocumentRequest(graph_store=store, site=SITE, agent=StubAgent(), settings={"run_id": "1"})
    document = build_export_graph(request)
    content = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    html_path = tmp_path / "graph.html"
    html_path.write_text(render_graph_page(content, SITE), encoding="utf-8")
    return html_path, document


def test_family_param_opens_pre_filtered_to_that_family(tmp_path):
    html_path, document = _real_graph_page(tmp_path)
    componente_ids = {node["id"] for node in document["@graph"] if node["type"] == "Componente"}
    assert componente_ids  # the fixture actually produced at least one

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{html_path.as_uri()}?family=Componente")
        page.wait_for_timeout(400)
        visible_ids = set(page.evaluate("[...visibleIds]"))
        browser.close()

    assert visible_ids == componente_ids


def test_no_family_param_falls_back_to_the_structural_default(tmp_path):
    html_path, document = _real_graph_page(tmp_path)
    structural_ids = {node["id"] for node in document["@graph"] if node["type"] in ("Pantalla", "Modulo")}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.wait_for_timeout(400)
        visible_ids = set(page.evaluate("[...visibleIds]"))
        browser.close()

    assert visible_ids == structural_ids


def test_unknown_family_falls_back_to_the_structural_default(tmp_path):
    html_path, document = _real_graph_page(tmp_path)
    structural_ids = {node["id"] for node in document["@graph"] if node["type"] in ("Pantalla", "Modulo")}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{html_path.as_uri()}?family=NotARealType")
        page.wait_for_timeout(400)
        visible_ids = set(page.evaluate("[...visibleIds]"))
        browser.close()

    assert visible_ids == structural_ids
