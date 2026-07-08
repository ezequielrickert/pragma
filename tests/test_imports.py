import importlib

from src.core import bootstrap  # noqa: F401
from src.core.engine import Engine
from src.core.interfaces import Action, PageState, Scraper, parse_action
from src.core.registry import AGENT_REGISTRY, GENERATOR_REGISTRY, SCRAPER_REGISTRY


def test_imports():
    importlib.import_module('src.core.interfaces')
    importlib.import_module('src.scrapers.playwright_scraper')
    importlib.import_module('src.generators.prd_generator')


def test_registries_populated():
    assert "playwright" in SCRAPER_REGISTRY.names()
    assert "mock" in AGENT_REGISTRY.names()
    assert "simple" in GENERATOR_REGISTRY.names()


def test_parse_action():
    assert parse_action("GOTO https://a.com") == Action("goto", "https://a.com")
    assert parse_action("CLICK nav > a#home") == Action("click", "nav > a#home")
    assert parse_action("FINISH").kind == "finish"
    assert parse_action("garbage").kind == "unknown"


class StubScraper(Scraper):
    def navigate(self, url):
        return PageState(url=url, title="Stub", components=[], links=[])

    def click(self, selector):
        return self.get_state()

    def get_state(self):
        return PageState(url="https://stub", title="Stub")

    def close(self):
        pass


def test_engine_smoke(tmp_path):
    from src.generators.prd_generator import SimplePRDGenerator

    agent = AGENT_REGISTRY.create("mock")
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        max_iterations=1,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    prd_path = engine.run("https://stub.example")

    assert (tmp_path / "progress.md").exists()

    import pathlib

    assert pathlib.Path(prd_path).read_text(encoding="utf-8")
