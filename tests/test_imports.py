import importlib
from typing import List, Optional

from src.core import bootstrap  # noqa: F401
from src.core.engine import Engine
from src.core.interfaces import Action, Agent, PageState, Scraper, parse_action
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


class ScriptedAgent(Agent):
    """Returns each response in `script` in order, then FINISH forever after."""

    def __init__(self, script: List[str]) -> None:
        self.script = list(script)
        self.calls = 0

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        response = self.script[self.calls] if self.calls < len(self.script) else "FINISH"
        self.calls += 1
        return response


def test_loop_survives_malformed_action(tmp_path):
    """A garbage (non-GOTO/CLICK/FINISH) response should skip that iteration, not abort the run."""
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(
        [
            "Sure, here is my plan",  # _create_plan response, any text is fine
            "GOTO https://stub/page-a",  # iteration 1: valid
            "Here is a PROGRESS.md summary instead of an action",  # iteration 2: malformed
            "GOTO https://stub/page-b",  # iteration 3: valid again, loop must still run
            "FINISH",  # iteration 4
        ]
    )
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        max_iterations=5,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # Both valid GOTOs after the malformed response must have been recorded as visited.
    # (route keys are scheme-stripped for graph-node identity, see _clean_url)
    visited = {u for u, d in gen.routes.items() if d["status"] == "Finished"}
    assert "stub/page-a" in visited
    assert "stub/page-b" in visited


class RecordingAgent(Agent):
    """Records every system_instruction it was called with, then always FINISHes."""

    def __init__(self) -> None:
        self.system_instructions: List[Optional[str]] = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.system_instructions.append(system_instruction)
        return "FINISH"


def test_decision_prompt_excludes_progress_tracker_skill(tmp_path):
    """The per-iteration system_instruction must not tell the model to write PROGRESS.md.

    Regression test: the archaeology-progress-tracker skill's "Update PROGRESS.md
    with a table" instructions used to be injected alongside the GOTO/CLICK/FINISH
    format, causing models to emit progress tables instead of actions.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = RecordingAgent()
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=1
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # Calls in order: [0] _create_plan, [1] the per-iteration decision, [2] synthesis.
    decision_instruction = agent.system_instructions[1]
    assert decision_instruction is not None
    assert "Update PROGRESS.md" not in decision_instruction
    assert "GOTO" in decision_instruction


def test_plan_prompt_excludes_strict_action_format(tmp_path):
    """The planning call must not receive the "respond with exactly one line" rule.

    Regression test: that rule used to be baked into the shared archeologist_skill
    file, which _create_plan also used as its system_instruction - causing the
    model to collapse a multi-step plan into a single GOTO line instead of an
    actual plan, which then also went unused by the execution loop.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = RecordingAgent()
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=1
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    plan_instruction = agent.system_instructions[0]
    decision_instruction = agent.system_instructions[1]
    assert plan_instruction is not None
    assert "EXACTLY ONE line" not in plan_instruction
    assert decision_instruction is not None
    assert "EXACTLY ONE line" in decision_instruction


class FailingClickScraper(Scraper):
    """Every click raises, simulating a Playwright strict-mode selector failure."""

    def navigate(self, url):
        return PageState(url=url, title="Stub", components=[], links=[])

    def click(self, selector):
        raise RuntimeError(f"strict mode violation: {selector!r} resolved to 3 elements")

    def get_state(self):
        return PageState(url="https://stub", title="Stub")

    def close(self):
        pass


def test_failed_click_is_reported_not_silently_ignored(tmp_path):
    """A click that raises must be recorded as a failure with its real error message.

    Regression test: PlaywrightScraper.click() used to catch and print click
    failures itself, then return the unchanged page state anyway - making a
    failed click indistinguishable from a successful one that changed nothing.
    Now the failure propagates, and the generator must surface why it failed.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(
        [
            "plan",
            "CLICK nav > a",  # will raise inside the scraper
            "FINISH",
        ]
    )
    scraper = FailingClickScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=3,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert "strict mode violation" in log_content


def test_iteration_prompt_is_bounded_by_batch_size(tmp_path):
    """A huge site (many pending routes/components) must not blow up prompt size.

    Also a regression test for prompt verbosity: DNA components used to be
    dumped as full JSON (CSS path + attributes.class), and a single long path
    or CSS-framework class string could dwarf the count-based batch_size cap.
    They're now a short numbered list (tag + text only) - the full path is
    only kept internally, for resolving a CLICK <number> back to a selector.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(["plan"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), batch_size=5
    )

    # Simulate a large site: 300 pending routes discovered.
    for i in range(300):
        gen._add_route(f"https://stub/page-{i}")

    huge_state = PageState(
        url="https://stub",
        title="Huge",
        components=[
            {
                "tag": "a",
                "text": f"c{i}",
                "path": f"body > div:nth-of-type({i}) > nav > a:nth-of-type({i})",
                "attributes": {"class": "utility-class-string " * 10},
            }
            for i in range(300)
        ],
        links=[],
    )
    prompt = gen._build_iteration_prompt(huge_state)

    # route keys are scheme-stripped for graph-node identity, see _clean_url
    assert prompt.count("stub/page-") == 5
    assert prompt.count("<a>") == 5  # 5 numbered DNA entries shown
    assert "300" in prompt  # totals still surfaced, just not the full lists
    assert "nth-of-type" not in prompt  # CSS paths never shown to the model
    assert "utility-class-string" not in prompt  # nor attributes.class


def test_click_target_resolves_by_index(tmp_path):
    """CLICK <number> must resolve to the real CSS path from the last DNA list shown.

    Regression test: the model used to have to reproduce a full CSS path (or
    class-based selector) verbatim to CLICK something - now it just picks a
    number from the list it was shown, and the generator maps that back to
    the actual selector before handing it to the scraper.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class RecordingClickScraper(Scraper):
        def __init__(self):
            self.clicked_selectors: List[str] = []

        def navigate(self, url):
            return PageState(
                url=url,
                title="Stub",
                components=[
                    {"tag": "button", "text": "First", "path": "body > button:nth-of-type(1)"},
                    {"tag": "button", "text": "Second", "path": "body > button:nth-of-type(2)"},
                ],
                links=[],
            )

        def click(self, selector):
            self.clicked_selectors.append(selector)
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    agent = ScriptedAgent(["plan", "CLICK 2", "FINISH"])
    scraper = RecordingClickScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=3
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert scraper.clicked_selectors == ["body > button:nth-of-type(2)"]
    assert gen.graph_edges[0]["component"] == '<button> "Second"'


def test_graph_edges_are_recorded_and_written(tmp_path):
    """Every successful action must be recorded as a from/action/to graph edge.

    Regression test: the codebase only tracked route *status* (pending/visited),
    not which component/action led from which page to which page - i.e. the
    navigation graph itself. Edges are collected in memory and written as JSON.
    """
    import json as json_module

    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(
        [
            "plan",
            "GOTO https://stub/page-a",
            "GOTO https://stub/page-b",
            "FINISH",
        ]
    )
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        graph_log_file=str(tmp_path / "graph.json"),
        max_iterations=5,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert len(gen.graph_edges) == 2
    # from/to are scheme-stripped graph-node keys, see _clean_url
    assert gen.graph_edges[0] == {
        "from": "stub.example",
        "component": "direct navigation (no known link label)",
        "action": "GOTO https://stub/page-a",
        "to": "stub/page-a",
    }
    assert gen.graph_edges[1]["from"] == "stub/page-a"
    assert gen.graph_edges[1]["to"] == "stub/page-b"

    written = json_module.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert written == gen.graph_edges


def test_graph_edge_records_component_used_to_navigate(tmp_path):
    """A GOTO to a previously-discovered link must record that link's visible text.

    Regression test / feature: knowing a route exists isn't the same as
    knowing *which component* led there. When a route was discovered via a
    real `<a>` link (label captured in `_update_discovered_routes`), the graph
    edge and progress log for the GOTO that visits it should say so.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(["plan", "GOTO https://stub/about", "FINISH"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=3,
    )
    # Simulate the link having been discovered on an earlier page, with its label.
    gen._add_route("https://stub/about", context="https://stub.example", label="About Us")

    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert gen.graph_edges[0]["component"] == 'link "About Us"'
    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert 'Component: link "About Us"' in log_content


def test_scheme_variants_of_same_url_are_one_graph_node(tmp_path):
    """http:// and https:// variants of the same URL must be treated as one node.

    Regression test: a route discovered as http://example.com/x (e.g. a stale
    link on the page) that resolves to https://example.com/x after redirect
    was never marked visited under its original http:// key - it stayed
    "Pending" forever, and the crawler would loop between the two scheme
    variants of the exact same page indefinitely.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    scraper = StubScraper()
    gen = SimplePRDGenerator(ScriptedAgent([]), scraper, progress_file=str(tmp_path / "p.md"))

    gen._add_route("http://stub/page")  # discovered via a non-https link
    assert gen._already_visited("https://stub/page") is False

    gen._add_route("https://stub/page", status="Finished")  # visited via its canonical form
    assert gen._already_visited("http://stub/page") is True
    assert gen._already_visited("https://stub/page/") is True  # trailing slash too


def test_already_visited_goto_is_skipped_without_renavigating(tmp_path):
    """A GOTO to an already-visited node must not trigger another page load.

    This is the explicit graph-traversal guard on top of the "Pending" list
    already excluding visited routes - it catches cases like scheme
    duplicates or a model that just doesn't follow instructions, without
    wasting a real navigation.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class CountingScraper(Scraper):
        def __init__(self):
            self.navigate_calls: List[str] = []

        def navigate(self, url):
            self.navigate_calls.append(url)
            return PageState(url=url, title="Stub", components=[], links=[])

        def click(self, selector):
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    agent = ScriptedAgent(
        [
            "plan",
            "GOTO https://stub/page-a",  # iteration 1: real navigation
            "GOTO http://stub/page-a",  # iteration 2: same node, different scheme - must be skipped
            "FINISH",
        ]
    )
    scraper = CountingScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=4
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # Root + the one real GOTO - the repeat (scheme-variant) GOTO never hit the scraper.
    assert scraper.navigate_calls == ["https://stub.example", "https://stub/page-a"]


def test_progress_log_is_append_only(tmp_path):
    """progress_log_file must accumulate every stage, unlike progress_file which is overwritten."""
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(
        [
            "plan",  # _create_plan
            "GOTO https://stub/page-a",  # iteration 1
            "FINISH",  # iteration 2
        ]
    )
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=5,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    # All stages must be present in one accumulated file, in order.
    assert "## DISCOVERY" in log_content
    assert "## PLAN CREATED" in log_content
    assert "## ITERATION 1" in log_content
    assert "## ITERATION 2" in log_content
    assert "## SYNTHESIS" in log_content
    assert log_content.index("## DISCOVERY") < log_content.index("## PLAN CREATED")
    assert log_content.index("## ITERATION 1") < log_content.index("## ITERATION 2")

    # progress_file (the live snapshot) must NOT contain every stage - only the last one.
    snapshot_content = (tmp_path / "progress.md").read_text(encoding="utf-8")
    assert "## Log: DISCOVERY" not in snapshot_content


def test_discover_components_produces_unique_clickable_selectors(tmp_path):
    """Sibling elements without ids must get distinct, individually-clickable selectors.

    Regression test: the DOM path builder only added #id when present, so any
    sibling elements without ids (e.g. every link/button in a real nav menu)
    produced identical path strings - which then failed as CSS selectors with
    a Playwright strict-mode "resolved to N elements" error on click, silently
    swallowed by the old click() implementation.
    """
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        "<html><body><nav>"
        '<button class="item">Option A</button>'
        '<button class="item">Option B</button>'
        '<button class="item">Option C</button>'
        "</nav></body></html>",
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        paths = [c["path"] for c in state.components if c["tag"] == "button"]

        assert len(paths) == 3
        assert len(set(paths)) == 3  # all distinct - this was the bug

        for path in paths:
            scraper.click(path)  # must not raise a strict-mode violation
    finally:
        scraper.close()


def test_click_falls_back_to_forced_click_when_not_visible(tmp_path):
    """A visually-hidden element (e.g. a dropdown submenu link) must still be clickable.

    Regression test: real nav dropdowns/mega-menus commonly keep submenu items
    in the DOM but visually hidden (visibility:hidden, zero-height container)
    until a parent is hovered. Playwright's default click() refuses to click
    something it can't see and times out after ~5s - this used to surface as
    a generic click failure with no recovery, even though the element is a
    perfectly real, present target.
    """
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        '<html><body><button id="hidden-btn" style="visibility:hidden;">Hidden</button>'
        "</body></html>",
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        path = next(c["path"] for c in state.components if c["tag"] == "button")
        scraper.click(path)  # must not raise - falls back to a forced click
    finally:
        scraper.close()


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
