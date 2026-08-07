"""Tests for safe mode: blocking (rather than executing) a click/submit that looks
like it would mutate real state - src/generators/component_classifier.classify_mutation_risk
and SimplePRDGenerator._is_mutating_action/_block_mutation."""
from src.core.interfaces import PageState, Scraper
from src.core.engine import Engine
from src.generators.component_classifier import classify_mutation_risk
from src.generators.prd_generator import SimplePRDGenerator
from tests.test_imports import ScriptedAgent, StubScraper


# --- component_classifier.classify_mutation_risk (pure, no scraper/agent) ---


def test_classify_mutation_risk_flags_post_forms():
    assert classify_mutation_risk({"form_method": "post", "text": "Guardar"}) == (
        "its enclosing form submits via POST"
    )


def test_classify_mutation_risk_never_flags_get_forms():
    assert classify_mutation_risk({"form_method": "get", "text": "Buscar"}) is None
    assert classify_mutation_risk({"form_method": "", "text": "Buscar"}) is None


def test_classify_mutation_risk_flags_business_verbs_without_a_form():
    """The common SPA pattern: a button with no real <form>, wired to call an
    API directly from onClick - the POST-form signal alone can't see this."""
    reason = classify_mutation_risk({"form_method": "", "text": "Confirmar pedido"})
    assert reason is not None
    assert "mutation verb" in reason


def test_classify_mutation_risk_ignores_generic_submit_verbs():
    """"enviar"/"submit"/"send" are deliberately excluded - they appear on
    essentially every harmless contact/newsletter form."""
    assert classify_mutation_risk({"form_method": "", "text": "Enviar"}) is None
    assert classify_mutation_risk({"form_method": "", "text": "Submit"}) is None
    assert classify_mutation_risk({"form_method": "", "text": "Send"}) is None


def test_classify_mutation_risk_checks_aria_label_too():
    reason = classify_mutation_risk(
        {"form_method": "", "text": "", "attributes": {"aria-label": "Eliminar cuenta"}}
    )
    assert reason is not None


def test_classify_mutation_risk_none_for_harmless_navigation_component():
    assert classify_mutation_risk({"form_method": "", "text": "Ver más productos"}) is None


# --- SimplePRDGenerator wiring (safe_mode on/off, end to end) ---


class _MutatingButtonScraper(Scraper):
    """A single page with one button whose enclosing form posts - clicking it
    would, in a real browser, submit real state."""

    def __init__(self) -> None:
        self.clicked = False

    def navigate(self, url):
        return PageState(
            url="https://stub",
            title="Stub",
            components=[
                {
                    "tag": "button", "text": "Confirmar pedido", "path": "button#confirm",
                    "form_method": "post",
                }
            ],
            links=[],
        )

    def click(self, selector):
        self.clicked = True
        return PageState(url="https://stub", title="Stub", components=[], links=[])

    def get_state(self):
        return PageState(url="https://stub", title="Stub")

    def close(self):
        pass


def test_safe_mode_blocks_a_post_form_click_by_default(tmp_path):
    scraper = _MutatingButtonScraper()
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH"])
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "p.md"), max_iterations=5
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # The real click must never have reached the scraper.
    assert scraper.clicked is False
    assert len(gen._mutation_boundaries) == 1
    assert gen._mutation_boundaries[0]["reason"] == "its enclosing form submits via POST"

    states = gen.graph_store.get_component_states(gen.base_domain, "stub")
    assert states["button#confirm"]["excluded_from_debt"] is True
    # A permanently-blocked action must never demand its own interaction.
    assert gen.graph_store.get_pages_with_unexplored_components(gen.base_domain) == []


def test_unsafe_mode_executes_the_action_normally(tmp_path):
    """safe_mode=False must restore the exact pre-existing behavior - the click
    actually reaches the scraper."""
    scraper = _MutatingButtonScraper()
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH"])
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "p.md"), max_iterations=5, safe_mode=False
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert scraper.clicked is True
    assert gen._mutation_boundaries == []


def test_safe_mode_report_includes_mutation_boundaries_section(tmp_path):
    scraper = _MutatingButtonScraper()
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH"])
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "p.md"), max_iterations=5
    )

    report = gen.generate_prd("https://stub.example")

    assert "Safe Mode: Detected Mutation Boundaries" in report
    assert "Confirmar pedido" in report
    assert "not executed" in report


def test_safe_mode_report_omits_section_when_nothing_was_blocked(tmp_path):
    gen = SimplePRDGenerator(
        ScriptedAgent(["plan", "FINISH"]), StubScraper(), progress_file=str(tmp_path / "p.md")
    )
    report = gen.generate_prd("https://stub.example")
    assert "Mutation Boundaries" not in report


def test_safe_mode_never_blocks_fill(tmp_path):
    """Typing into a field never submits anything by itself - only click/submit
    are checked (see the _execute_loop call site)."""

    class FormFieldScraper(Scraper):
        def __init__(self) -> None:
            self.filled = False

        def navigate(self, url):
            return PageState(
                url="https://stub",
                title="Stub",
                components=[
                    {"tag": "input", "text": "", "path": "input#name", "form_method": "post",
                     "input_type": "text"}
                ],
                links=[],
            )

        def fill(self, selector, value):
            self.filled = True
            return PageState(url="https://stub", title="Stub", components=[], links=[])

        def click(self, selector):
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    scraper = FormFieldScraper()
    agent = ScriptedAgent(["plan", '{"action": "fill", "ref": 1, "value": "Ana"}', "FINISH"])
    gen = SimplePRDGenerator(agent, scraper, progress_file=str(tmp_path / "p.md"), max_iterations=5)
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert scraper.filled is True
    assert gen._mutation_boundaries == []
