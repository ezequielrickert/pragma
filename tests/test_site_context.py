"""Tests for Fase 0: the whole-run "what is this site/app for" grounding text
(SimplePRDGenerator._establish_site_context / _site_context_line), distinct from
PageState.description's per-page, per-turn context line."""
from src.core.interfaces import PageState, Scraper
from src.generators.prd_generator import SimplePRDGenerator
from tests.test_imports import ScriptedAgent, StubScraper


class ContextAwareScraper(Scraper):
    """A minimal Scraper that *does* implement extract_context, unlike StubScraper -
    exercises the "happy path" of _establish_site_context."""

    def __init__(self, context_text: str) -> None:
        self.context_text = context_text

    def navigate(self, url):
        return PageState(url=url, title="Stub", components=[], links=[], description="short desc")

    def click(self, selector):
        return self.get_state()

    def get_state(self):
        return PageState(url="https://stub", title="Stub")

    def close(self):
        pass

    def extract_context(self, max_chars: int = 1500) -> str:
        return self.context_text[:max_chars]


def test_establish_site_context_uses_scrapers_extract_context(tmp_path):
    scraper = ContextAwareScraper(
        "Headings: Empanadas caseras | Nuestros sabores\nHacemos pedidos a domicilio de empanadas."
    )
    agent = ScriptedAgent(["plan", "FINISH"])
    gen = SimplePRDGenerator(agent, scraper, progress_file=str(tmp_path / "p.md"))

    gen.generate_prd("https://stub.example")

    assert "empanadas" in gen.site_context.lower()
    # Must be surfaced in the persistent per-iteration line, not just stored.
    assert "Site purpose" in gen._site_context_line()
    assert gen.site_context in gen._site_context_line()


def test_establish_site_context_falls_back_when_scraper_does_not_implement_it(tmp_path):
    """StubScraper doesn't override extract_context (inherits the ABC's
    NotImplementedError default) - must degrade to PageState.description, not crash
    the run. This is the RestScraper-equivalent gap documented in
    docs/explicativos/pendientes-futuras-fases.md."""
    scraper = StubScraper()
    agent = ScriptedAgent(["plan", "FINISH"])
    gen = SimplePRDGenerator(agent, scraper, progress_file=str(tmp_path / "p.md"))

    gen.generate_prd("https://stub.example")

    # StubScraper.navigate() returns description="" (the PageState default) -
    # nothing usable to fall back to, but the run must still complete cleanly.
    assert gen.site_context == ""
    assert gen._site_context_line() == ""


def test_deep_context_false_skips_extraction_entirely(tmp_path):
    scraper = ContextAwareScraper("This text must never be read.")
    agent = ScriptedAgent(["plan", "FINISH"])
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "p.md"), deep_context=False
    )

    gen.generate_prd("https://stub.example")

    assert gen.site_context == ""


def test_site_context_line_is_included_in_every_iteration_prompt(tmp_path):
    """Unlike the per-page description (only shown while on that page), the site
    context must persist across turns - built directly, without a full run, to
    check the exact prompt text _build_iteration_prompt produces."""
    scraper = ContextAwareScraper("Vende empanadas caseras y hace envios a domicilio.")
    agent = ScriptedAgent([])
    gen = SimplePRDGenerator(agent, scraper, progress_file=str(tmp_path / "p.md"))
    gen.base_domain = "stub.example"
    gen.site_context = "Vende empanadas caseras y hace envios a domicilio."

    prompt = gen._build_iteration_prompt(PageState(url="https://stub.example", title="Home"))

    assert "Site purpose (established from the landing page): Vende empanadas" in prompt
