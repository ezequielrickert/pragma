import importlib
import json
from typing import Any, Dict, List, Optional

from src.core import bootstrap  # noqa: F401
from src.core.engine import Engine
from src.core.interfaces import (
    Action,
    Agent,
    AgentAction,
    PageState,
    Scraper,
    parse_action,
    parse_agent_action,
)
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


def test_parse_agent_action_prefers_json_object():
    action = parse_agent_action('{"action": "click", "ref": 3}')
    assert action == AgentAction(kind="click", ref=3, raw='{"action": "click", "ref": 3}')

    action = parse_agent_action('{"action": "fill", "ref": 2, "value": "hi"}')
    assert action.kind == "fill"
    assert action.ref == 2
    assert action.value == "hi"

    action = parse_agent_action('{"action": "navigate", "url": "example.com/about"}')
    assert action.kind == "navigate"
    assert action.url == "example.com/about"

    action = parse_agent_action('{"action": "goto", "url": "example.com"}')
    assert action.kind == "navigate"  # legacy "goto" name normalized to "navigate"

    assert parse_agent_action('{"action": "finish"}').kind == "finish"


def test_parse_agent_action_falls_back_to_legacy_text_grammar():
    """A model that ignores the JSON instruction and replies with the old
    GOTO/CLICK/FILL/SUBMIT/FINISH text grammar must still be understood."""
    assert parse_agent_action("GOTO https://a.com") == AgentAction(
        kind="navigate", url="https://a.com", raw="GOTO https://a.com"
    )
    assert parse_agent_action("CLICK 3") == AgentAction(kind="click", ref=3, raw="CLICK 3")
    assert parse_agent_action("FILL 2 hello world") == AgentAction(
        kind="fill", ref=2, value="hello world", raw="FILL 2 hello world"
    )
    assert parse_agent_action("SUBMIT 2") == AgentAction(kind="submit", ref=2, raw="SUBMIT 2")
    assert parse_agent_action("FINISH").kind == "finish"
    assert parse_agent_action("garbage").kind == "unknown"


def test_tool_block_text_lists_valid_help_topics_explicitly():
    """Regression test: a real model hallucinated help topic "navigation" (not a
    real one - navigate_usage is) because the text-fallback tool block only ever
    rendered parameter *names*, never the topic enum living in one parameter's
    description string - so a backend on the text-fallback path never saw the
    valid list at all. It must now get its own explicit, always-rendered line."""
    from src.core.interfaces import HELP_TOPICS, TOOL_SPECS, _tool_block_text

    block = _tool_block_text(TOOL_SPECS)
    assert "Valid help topics" in block
    for topic in HELP_TOPICS:
        assert topic in block


def test_local_agent_help_tool_schema_has_real_enum():
    """Regression test, native tool-calling path: `topic` must be a real JSON-schema
    `enum`, not just prose in its description - a structural constraint some
    servers/models actually honor during tool-call generation, unlike prose."""
    from src.agents.local_agent import LocalAgent
    from src.core.interfaces import HELP_TOPICS, TOOL_SPECS

    help_tool = next(t for t in TOOL_SPECS if t["name"] == "help")
    schema = LocalAgent._to_openai_tool(help_tool)
    assert schema["function"]["parameters"]["properties"]["topic"]["enum"] == HELP_TOPICS


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
    rows = gen.graph_store.get_progress_table_rows(gen.base_domain)
    visited = {r["url"] for r in rows if r["status"] == "Finished"}
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
    with a table" instructions used to be injected alongside the action-format
    instructions, causing models to emit progress tables instead of actions.
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
    # The per-iteration call goes through Agent.act(), whose default implementation
    # (see TOOL_SPECS/_tool_block_text in src/core/interfaces.py) appends a compact
    # tool-description block naming "navigate" to whatever system_instruction it's given.
    decision_instruction = agent.system_instructions[1]
    assert decision_instruction is not None
    assert "Update PROGRESS.md" not in decision_instruction
    assert "navigate" in decision_instruction


def test_plan_prompt_excludes_strict_action_format(tmp_path):
    """The planning call must not receive the "respond with one JSON action" rule.

    Regression test: a strict single-line action-format rule used to be baked
    into the shared archeologist_skill file, which _create_plan also used as
    its system_instruction - causing the model to collapse a multi-step plan
    into a single command instead of an actual plan, which then also went
    unused by the execution loop. That rule now lives in Agent.act()'s tool
    block (see TOOL_SPECS/_tool_block_text), which only the per-iteration
    decision call goes through - _create_plan calls agent.generate() directly.
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
    assert "EXACTLY ONE JSON object" not in plan_instruction
    assert decision_instruction is not None
    assert "EXACTLY ONE JSON object" in decision_instruction


class FailingClickScraper(Scraper):
    """Every click raises, simulating a Playwright strict-mode selector failure."""

    def navigate(self, url):
        return PageState(
            url=url,
            title="Stub",
            components=[{"tag": "a", "text": "Broken link", "path": "nav > a"}],
            links=[],
        )

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
            "CLICK 1",  # resolves to the one DNA element shown, then raises inside the scraper
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
        gen._upsert(f"https://stub/page-{i}")

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


def test_revealed_dropdown_item_surfaces_even_when_deep_in_dom_order(tmp_path):
    """A just-revealed, currently-visible element must outrank an
    already-shown one for a batch_size slot, even if it's much later in raw
    DOM order.

    Regression test for a real stuck-loop found crawling austral.edu.ar: a
    mega-menu trigger was element #8 in DOM order, but its own submenu items
    (present in the DOM the whole time, just CSS-hidden) were #273+ - with
    batch_size=20 and pure DOM-order slicing, the model could click the
    trigger endlessly and never once see what it revealed, since the same
    first 20 elements were shown every iteration regardless of what had just
    become visible on screen.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(["plan"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), batch_size=3
    )

    def state_with(menu_item_visible: bool) -> PageState:
        components = [
            {"tag": "a", "text": "Skip link", "path": "a#skip", "visible": True},
            {"tag": "a", "text": "Logo", "path": "a#logo", "visible": True},
            {"tag": "a", "text": "Institucional", "path": "a#trigger", "visible": True},
        ] + [
            # Filler elements standing in for the other ~260 DOM nodes between
            # the trigger and its own submenu on the real page - empirically
            # (see the live-site repro this test is based on) those are mostly
            # *other* closed menus' items: present, but still CSS-hidden too.
            {"tag": "a", "text": f"filler {i}", "path": f"a#filler{i}", "visible": False}
            for i in range(5)
        ] + [
            {
                "tag": "a",
                "text": "Acerca de la universidad",
                "path": "a#menu-item",
                "visible": menu_item_visible,
            }
        ]
        return PageState(url="https://stub", title="Stub", components=components, links=[])

    # Before the trigger is clicked: the menu item is present but hidden, and
    # far past batch_size=3 in DOM order - correctly not shown.
    prompt_before = gen._build_iteration_prompt(state_with(menu_item_visible=False))
    assert "Institucional" in prompt_before
    assert "Acerca de la universidad" not in prompt_before

    # Simulate the trigger having just been clicked: the menu item is now
    # visible. Even though it's still #9 in DOM order and batch_size is only
    # 3, it must now win a slot over the already-shown filler elements.
    prompt_after = gen._build_iteration_prompt(state_with(menu_item_visible=True))
    assert "Acerca de la universidad" in prompt_after


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
    assert gen.graph_store.get_edges(gen.base_domain)[0]["component"] == '<button> "Second"'


def test_repeated_inplace_click_target_is_blocked(tmp_path):
    """Immediately re-clicking the exact same non-navigating target must be
    blocked, not executed a second time.

    Regression test for a real stuck loop found crawling austral.edu.ar: a
    dropdown trigger ("Academic Offerings") revealed new submenu items on the
    first click, but the model then re-clicked the *same trigger* on the next
    iteration - which, verified against the live site, actually closes part
    of what it just opened (a toggle), oscillating forever instead of ever
    clicking one of the newly revealed items.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class ToggleMenuScraper(Scraper):
        """A trigger that reveals a new item in place (no navigation); the
        item itself is a real link that navigates elsewhere."""

        def __init__(self):
            self.clicked_selectors: List[str] = []
            self._state = PageState(
                url="https://stub",
                title="Stub",
                components=[{"tag": "a", "text": "trigger", "path": "a#trigger"}],
                links=[],
            )

        def navigate(self, url):
            return self._state

        def click(self, selector):
            self.clicked_selectors.append(selector)
            if selector == "a#trigger":
                self._state = PageState(
                    url="https://stub",  # unchanged - a toggle, not a navigation
                    title="Stub",
                    components=[
                        {"tag": "a", "text": "trigger", "path": "a#trigger"},
                        {"tag": "a", "text": "item", "path": "a#item"},
                    ],
                    links=[],
                )
            elif selector == "a#item":
                self._state = PageState(url="https://stub/leaf", title="Leaf", components=[], links=[])
            return self._state

        def get_state(self):
            return self._state

        def close(self):
            pass

    # iter1 dna={1: trigger} -> CLICK 1 opens it (in-place).
    # iter2 dna={1: item (never interacted, prioritized), 2: trigger (just
    #   interacted with) -> CLICK 2 attempts to repeat the trigger - must be
    #   blocked (see _select_dna_components: an item is prioritized ahead of
    #   an already-*interacted-with* component the moment it's revealed, not
    #   just ahead of an already-*shown* one, so it stays at slot 1 even after
    #   being displayed once in a blocked iteration).
    # iter3 dna={1: item, 2: trigger} (unchanged - the blocked click didn't
    #   interact with anything) -> CLICK 1 clicks the item instead, which
    #   really navigates.
    agent = ScriptedAgent(["plan", "CLICK 1", "CLICK 2", "CLICK 1", "FINISH"])
    scraper = ToggleMenuScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=5,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # The trigger was clicked exactly once - the attempted repeat never
    # reached the scraper at all.
    assert scraper.clicked_selectors == ["a#trigger", "a#item"]

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert "repeats the previous iteration's target" in log_content


def test_component_ledger_tracks_interactions_and_is_written_to_disk(tmp_path):
    """Every shown component gets a ledger entry; only ones actually clicked/filled/
    submitted get interacted=True and a non-empty interaction history; the whole
    thing is written to components_log_file once the run finishes."""
    from src.generators.prd_generator import SimplePRDGenerator

    class ToggleMenuScraper(Scraper):
        def __init__(self):
            self._state = PageState(
                url="https://stub",
                title="Stub",
                components=[{"tag": "a", "text": "trigger", "path": "a#trigger"}],
                links=[],
            )

        def navigate(self, url):
            return self._state

        def click(self, selector):
            if selector == "a#trigger":
                self._state = PageState(
                    url="https://stub",
                    title="Stub",
                    components=[
                        {"tag": "a", "text": "trigger", "path": "a#trigger"},
                        {"tag": "a", "text": "item", "path": "a#item"},
                    ],
                    links=[],
                )
            return self._state

        def get_state(self):
            return self._state

        def close(self):
            pass

    # iter1: only "trigger" exists -> CLICK 1 clicks it, revealing "item".
    # iter2: dna reorders to [1: item (unseen, prioritized), 2: trigger
    # (already shown)] -> CLICK 2 attempts to repeat the trigger and is
    # blocked by the repeat-target guard (see test_repeated_inplace_click_
    # target_is_blocked) - never reaches the scraper, so "item" stays
    # unclicked and "trigger" keeps exactly its one real interaction.
    agent = ScriptedAgent(["plan", "CLICK 1", "CLICK 2", "FINISH"])
    scraper = ToggleMenuScraper()
    components_log = tmp_path / "components.json"
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        components_log_file=str(components_log),
        max_iterations=3,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    ledger = json.loads(components_log.read_text(encoding="utf-8"))
    page = ledger["stub"]
    assert page["a#trigger"]["interacted"] is True
    assert page["a#trigger"]["interactions"] == [
        {"action": "click", "value": None, "resulting_url": "stub"}
    ]
    # Shown (revealed by the trigger click) but never itself clicked - present,
    # not interacted.
    assert page["a#item"]["interacted"] is False
    assert page["a#item"]["interactions"] == []


def test_finish_is_rejected_on_the_very_first_turn_with_unshown_components(tmp_path):
    """FINISH as the model's very first response must be blocked if the root
    page has real components it has never been shown before - turn one is not
    exempt from "investigate before finishing."

    Regression test for a real crawl (empanad.app): the root page had 3
    components and 0 links (an SPA with no <a> tags at all, so Pending routes
    is empty from the start); the model's first response was `finish`, and it
    was accepted - the previous version of this guard suppressed the
    new-component count specifically on the first prompt of the run, on the
    theory that everything is trivially "new" on turn one and that's not
    itself suspicious. That reasoning is wrong for this guard's actual job:
    "has this ever been looked at" is exactly as unanswered on turn one as on
    any later turn.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class RootOnlyScraper(Scraper):
        """Neither button navigates or changes the DOM - both stay present
        (and clickable again) for the lifetime of the page."""

        def _state(self) -> PageState:
            return PageState(
                url="https://stub",
                title="Stub",
                components=[
                    {"tag": "button", "text": "one", "path": "button#one"},
                    {"tag": "button", "text": "two", "path": "button#two"},
                ],
                links=[],
            )

        def navigate(self, url):
            return self._state()

        def click(self, selector):
            return self._state()

        def get_state(self):
            return self._state()

        def close(self):
            pass

    # iter1: FINISH rejected immediately - neither button has ever been
    # interacted with, even though this is the very first turn. iter2-3:
    # click each button in turn (always slot 1, since an un-interacted
    # component always outranks an interacted one). iter4: FINISH succeeds.
    agent = ScriptedAgent(["plan", "FINISH", "CLICK 1", "CLICK 1", "FINISH"])
    scraper = RootOnlyScraper()
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
    assert "finish rejected" in log_content
    assert "remain unexplored" in log_content
    # The final FINISH must succeed, once every real component has actually
    # been clicked - not merely shown.
    assert "Agent concluded research" in log_content


def test_finish_is_rejected_when_new_components_just_appeared(tmp_path):
    """FINISH must be blocked when the model's last action revealed brand-new,
    never-interacted-with components on the same URL - and allowed only once
    those components have actually been clicked, not merely displayed.

    Regression test for two real crawls: (1) empanad.app - clicking submit
    with only one of two fields filled changed the page from 3 to 11
    components (still the same URL, on a single-page app that never has a
    non-empty Pending routes list at all), and the model concluded research
    on the very next turn without a single turn spent looking at what had
    just appeared; (2) a later run on the same site where the model filled
    one field, was shown two other real components, and finished anyway - the
    guard's original version only required a component to have been *shown*
    once (informational, not enforced), which turned out to be exactly as
    easy to sail past as no check at all. It now requires actual interaction.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class RevealOnSubmitScraper(Scraper):
        def __init__(self):
            self._state = PageState(
                url="https://stub",
                title="Stub",
                components=[{"tag": "button", "text": "submit", "path": "button#submit"}],
                links=[],
            )

        def navigate(self, url):
            return self._state

        def click(self, selector):
            # Clicking submit reveals new components in place - no navigation,
            # same shape as the real empanad.app crawl. Later clicks (on the
            # revealed components themselves) don't change the shape further.
            self._state = PageState(
                url="https://stub",
                title="Stub",
                components=[
                    {"tag": "button", "text": "submit", "path": "button#submit"},
                    {"tag": "div", "text": "new-1", "path": "div#new-1"},
                    {"tag": "div", "text": "new-2", "path": "div#new-2"},
                ],
                links=[],
            )
            return self._state

        def get_state(self):
            return self._state

        def close(self):
            pass

    # iter1: CLICK 1 (submit) reveals new-1/new-2. iter2: FINISH rejected -
    # new-1/new-2 have been shown but never interacted with. iter3-4: CLICK 1
    # twice more - _select_dna_components always ranks the highest-priority
    # un-interacted component at slot 1, so two more "CLICK 1"s reach new-1
    # then new-2 regardless of exact tie-break ordering. iter5: FINISH now
    # succeeds - every real component on the page has actually been clicked.
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH", "CLICK 1", "CLICK 1", "FINISH"])
    scraper = RevealOnSubmitScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=6,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert "finish rejected" in log_content
    assert "remain unexplored" in log_content
    assert "Agent concluded research" in log_content  # the final FINISH must succeed


def test_finish_is_rejected_when_a_left_behind_page_has_unexplored_components(tmp_path):
    """FINISH must be blocked while a page the agent has already navigated away
    from still has a real, un-interacted-with component on it - and the
    already-visited navigate-decline guard must let a revisit back to that
    page through, specifically because of that debt.

    This is the concrete regression test for the core "keep track of all
    branches" ask: a component shown-but-not-interacted-with on page A must
    still be enforceable after the agent has moved on to page B, something an
    in-process, current-page-only ledger could never do (see
    GraphStore.get_pages_with_unexplored_components /
    page_has_unexplored_components, consulted by _reject_premature_finish and
    the navigate-decline guard in _execute_loop).
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class TwoPageScraper(Scraper):
        def __init__(self):
            self.navigate_calls: List[str] = []

        def navigate(self, url):
            self.navigate_calls.append(url)
            return PageState(
                url="https://stub/page-a",
                title="A",
                components=[
                    {"tag": "a", "text": "leave", "path": "a#leave"},
                    {"tag": "button", "text": "unexplored", "path": "button#unexplored"},
                ],
                links=[],
            )

        def click(self, selector):
            if selector == "a#leave":
                return PageState(url="https://stub/page-b", title="B", components=[], links=[])
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub/page-a", title="A")

        def close(self):
            pass

    # iter1: CLICK 1 ("leave") navigates to page-b, leaving "unexplored"
    # (button#unexplored) untouched on page-a. iter2: FINISH must be rejected
    # (page-a has debt on a page that isn't even the current one). iter3: GOTO
    # stub/page-a must be allowed through the navigate-decline guard despite
    # page-a being already Finished, specifically because of that debt.
    # iter4: CLICK 1 now targets "unexplored" (an un-interacted component
    # always outranks an interacted one - "leave" was already clicked).
    # iter5: FINISH now succeeds - the debt is actually cleared, not just
    # revisited.
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH", "GOTO https://stub/page-a", "CLICK 1", "FINISH"])
    scraper = TwoPageScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=6,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example/page-a")

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert "pages you've already left have components that remain unexplored" in log_content
    assert "stub/page-a" in log_content
    assert "Agent concluded research" in log_content  # the final FINISH must succeed
    # The revisit GOTO must have actually reached the scraper (root nav + the
    # explicit revisit = 2 calls), not been silently skipped by the
    # already-visited guard - which is exactly what page_has_unexplored_
    # components is for.
    assert scraper.navigate_calls == ["https://stub.example/page-a", "https://stub/page-a"]


def test_finish_eventually_succeeds_on_a_page_that_never_converges(tmp_path):
    """A page whose component identities shift on every interaction (e.g. a
    quantity stepper whose sibling-index-based CSS paths change every time a
    row is added/removed) must not block `finish` forever - once its debt has
    failed to shrink for `max_stalled_finish_attempts` consecutive checks, the
    diminishing-returns guard must give up on it and let the run conclude.

    Regression test for two real crawls (empanad.app's "Agregar"/"Restar"
    stepper, mapadeprofesionales.com's repeated login-submit retries): both
    burned most of a run's iteration budget on one page that was never going
    to fully "converge," at the direct expense of exploring the rest of the
    site.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class ChurningStepperScraper(Scraper):
        """Every click both interacts with the current trigger AND spawns a
        brand-new, never-before-seen component path (simulating a stepper
        whose sibling-index-based path shifts every time a row is added) -
        the debt on this page can never reach zero."""

        def __init__(self):
            self.click_count = 0

        def navigate(self, url):
            return self._state()

        def _state(self) -> PageState:
            return PageState(
                url="https://stub",
                title="Stub",
                components=[
                    {"tag": "button", "text": "trigger", "path": "button#trigger"},
                    {"tag": "div", "text": f"row-{self.click_count}", "path": f"div#row{self.click_count}"},
                ],
                links=[],
            )

        def click(self, selector):
            self.click_count += 1
            return self._state()

        def get_state(self):
            return self._state()

        def close(self):
            pass

    # Every "CLICK 1" targets whatever un-interacted component currently sorts
    # first (always the freshly-spawned row - the trigger gets interacted
    # once and then stays deprioritized) - so debt never shrinks, it just
    # keeps respawning. max_stalled_finish_attempts=2 keeps the test fast.
    agent = ScriptedAgent(
        ["plan", "CLICK 1", "FINISH", "CLICK 1", "FINISH", "CLICK 1", "FINISH", "FINISH"]
    )
    scraper = ChurningStepperScraper()
    gen = SimplePRDGenerator(
        agent,
        scraper,
        progress_file=str(tmp_path / "progress.md"),
        progress_log_file=str(tmp_path / "progress_log.md"),
        max_iterations=10,
        max_stalled_finish_attempts=2,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert "finish rejected" in log_content
    assert "Gave up on" in log_content
    assert "Agent concluded research" in log_content


def test_goto_target_without_scheme_still_navigates(tmp_path):
    """A GOTO to a schemeless target must still reach the scraper as an absolute URL.

    Regression test: the Pending routes shown to the model are scheme-stripped
    graph-node keys (see _clean_url), so a model naturally echoes one back
    verbatim, e.g. `GOTO example.com/about` instead of `GOTO https://example.com/about`.
    Playwright can't navigate to a schemeless string - it must be resolved to an
    absolute URL before being handed to the scraper.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    class RecordingScraper(Scraper):
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

    agent = ScriptedAgent(["plan", "GOTO stub/page-a", "FINISH"])
    scraper = RecordingScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=3
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert scraper.navigate_calls == ["https://stub.example", "https://stub/page-a"]


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

    edges = gen.graph_store.get_edges(gen.base_domain)
    assert len(edges) == 2
    # from/to are scheme-stripped graph-node keys, see _clean_url
    assert edges[0] == {
        "from": "stub.example",
        "component": "direct navigation (no known link label)",
        "action": "GOTO https://stub/page-a",
        "to": "stub/page-a",
    }
    assert edges[1]["from"] == "stub/page-a"
    assert edges[1]["to"] == "stub/page-b"

    written = json_module.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert written == edges


def test_graph_edge_records_component_used_to_navigate(tmp_path):
    """A GOTO to a previously-discovered link must record that link's visible text.

    Regression test / feature: knowing a route exists isn't the same as
    knowing *which component* led there. When a link to the target was
    discovered specifically on the page being navigated *from* (recorded via
    `record_link` in `_update_discovered_routes`), the graph edge and progress
    log for the GOTO that visits it should say so. Looking up a label by
    destination page alone (rather than the specific from/to pair) used to
    misattribute a link discovered on some other page entirely as if it were
    on the current page - see wiki/graph-based-crawl-tracking.md.
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
    # Simulate the link having been discovered on the root page (the page the
    # GOTO below will actually navigate from), with its label. base_domain is
    # set manually here to match what generate_prd will compute from the root
    # url below, so this seed lands in the same site bucket.
    gen.base_domain = "stub.example"
    gen.graph_store.record_link(gen.base_domain, "stub.example", "stub/about", "About Us")

    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert gen.graph_store.get_edges(gen.base_domain)[0]["component"] == 'link "About Us"'
    log_content = (tmp_path / "progress_log.md").read_text(encoding="utf-8")
    assert 'Component: link "About Us"' in log_content


def test_goto_component_is_not_attributed_to_the_wrong_source_page(tmp_path):
    """A link discovered on page X must never be claimed as the component for a GOTO from page Y.

    Regression test for a real bug found crawling a live site: a route can be
    discovered (and thus labeled) via a link on one page, but later actually
    be reached by a GOTO issued from a completely different page. The old
    per-destination-page label lookup couldn't tell the two apart and
    reported the label from page X's link even when navigating from page Y,
    which doesn't have that link at all.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    agent = ScriptedAgent(["plan", "GOTO https://stub/target", "FINISH"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, progress_file=str(tmp_path / "progress.md"), max_iterations=3
    )
    gen.base_domain = "stub.example"
    # "target" was discovered on a page that is NOT the one we're about to
    # navigate from - its label must not leak into this GOTO's component.
    gen.graph_store.record_link(gen.base_domain, "some-other-page", "stub/target", "Ver agenda completa")

    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    component = gen.graph_store.get_edges(gen.base_domain)[0]["component"]
    assert component == "direct navigation (no known link label)"
    assert "Ver agenda completa" not in component


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

    gen._upsert("http://stub/page")  # discovered via a non-https link
    assert gen._already_visited("https://stub/page") is False

    gen._upsert("https://stub/page", status="Finished")  # visited via its canonical form
    assert gen._already_visited("http://stub/page") is True
    assert gen._already_visited("https://stub/page/") is True  # trailing slash too


def test_clean_url_keeps_hash_routes_distinct_but_collapses_anchors(tmp_path):
    """A hash-based SPA router's routes (`#/products/123`) must stay distinct
    graph nodes; a plain in-page anchor (`#section`) must still collapse into
    its base page, as before."""
    from src.generators.prd_generator import SimplePRDGenerator

    gen = SimplePRDGenerator(ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"))

    assert gen._clean_url("https://stub.example/app#/products/123") == "stub.example/app#/products/123"
    assert gen._clean_url("https://stub.example/app#/products/123/") == "stub.example/app#/products/123"
    # A bare anchor (no "/") is still treated as same-page scroll target, not a route.
    assert gen._clean_url("https://stub.example/page#section") == "stub.example/page"
    assert gen._clean_url("https://stub.example/page") == "stub.example/page"


def test_domain_in_scope_respects_allow_subdomains(tmp_path):
    from src.generators.prd_generator import SimplePRDGenerator

    exact_only = SimplePRDGenerator(ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p1.md"))
    exact_only.base_domain = "example.com"
    assert exact_only._domain_in_scope("example.com") is True
    assert exact_only._domain_in_scope("blog.example.com") is False
    assert exact_only._domain_in_scope("example.org") is False

    with_subdomains = SimplePRDGenerator(
        ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p2.md"), allow_subdomains=True
    )
    with_subdomains.base_domain = "example.com"
    assert with_subdomains._domain_in_scope("example.com") is True
    assert with_subdomains._domain_in_scope("blog.example.com") is True
    assert with_subdomains._domain_in_scope("www.example.com") is True
    assert with_subdomains._domain_in_scope("example.org") is False


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


def test_discover_components_reports_visibility(tmp_path):
    """`visible` must reflect actual CSS-driven visibility, not just DOM presence.

    Regression test companion to the austral.edu.ar stuck-loop bug: a
    dropdown's items are commonly rendered from page load, just hidden with
    `display:none` until a class toggle reveals them. `_select_dna_components`
    (prd_generator.py) relies on this field to prioritize what's actually
    on-screen - if it doesn't reflect the real display state, that fix is inert.
    """
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        "<html><body>"
        '<a id="always-visible" href="#">Always visible</a>'
        '<a id="menu-item" href="#" style="display:none;">Menu item</a>'
        "</body></html>",
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        by_id = {c["attributes"]["id"]: c for c in state.components}
        assert by_id["always-visible"]["visible"] is True
        assert by_id["menu-item"]["visible"] is False
    finally:
        scraper.close()


def test_discover_components_recovers_text_from_hidden_and_alt_sources(tmp_path):
    """A component with empty `innerText`/`aria-label` but a real accessible
    name elsewhere must not be discovered as blank.

    Regression test: a real crawl (empanad.app) hit a header `<a href="/">`
    wrapping only `<img alt="EmpanadApp">` - `innerText` is '' (an <img> has
    no text) and the <a> itself carries no aria-label, so the component
    catalog narrated it as "Unnamed Element"/"Empty Element" even though a
    real, recoverable label (the image's alt text) was one attribute away.
    Also covers the common accessible-icon-button pattern: a visually-hidden
    (`display:none`) label span with no aria-label on the button itself,
    which only the `textContent` last-resort fallback recovers.
    """
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        "<html><body>"
        '<a id="logo-link" href="#"><img src="logo.png" alt="EmpanadApp"></a>'
        '<button id="icon-btn"><svg></svg><span style="display:none;">Add flavor</span></button>'
        "</body></html>",
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        by_id = {c["attributes"]["id"]: c for c in state.components}
        assert by_id["logo-link"]["text"] == "EmpanadApp"
        assert by_id["icon-btn"]["text"] == "Add flavor"
    finally:
        scraper.close()


def test_discover_components_escapes_special_characters_in_ids(tmp_path):
    """A CSS-special character in an id (e.g. a colon) must not produce an
    invalid, unclickable selector.

    Regression test: component libraries like Radix UI generate ids such as
    "radix-:r0:" - legal in an HTML id attribute, but a colon starts a
    pseudo-class in a CSS selector. The path builder used to concatenate the
    raw id (`'#' + e.id`) into the selector, producing `#radix-:r0:` - which
    Playwright's selector engine rejects with "Unexpected token", making that
    element permanently unclickable regardless of which ref the model picked.
    """
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        '<html><body><input id="radix-:r0:" placeholder="search"></body></html>',
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        path = state.components[0]["path"]
        assert path == r"body > input#radix-\:r0\:"
        scraper.fill(path, "hello")  # must not raise a selector-syntax error
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


class JsonRecordingAgent(Agent):
    """Returns each response in `script` (already JSON action text) in order,
    recording the combined system_instruction it was called with each time -
    exercises the base Agent.act() default implementation directly."""

    def __init__(self, script: List[str]) -> None:
        self.script = list(script)
        self.calls = 0
        self.system_instructions: List[Optional[str]] = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.system_instructions.append(system_instruction)
        response = self.script[self.calls] if self.calls < len(self.script) else '{"action": "finish"}'
        self.calls += 1
        return response


def test_agent_act_default_parses_json_and_advertises_tools():
    """Agent.act()'s default implementation must append a tool block naming
    every TOOL_SPECS entry, and parse a JSON action reply back out."""
    agent = JsonRecordingAgent(['{"action": "click", "ref": 5}'])
    action = agent.act("some prompt", system_instruction="be a good archaeologist")
    assert action == AgentAction(kind="click", ref=5, raw='{"action": "click", "ref": 5}')

    combined = agent.system_instructions[0]
    assert "be a good archaeologist" in combined
    for name in ("navigate", "click", "fill", "submit", "finish"):
        assert name in combined


def test_error_feedback_is_surfaced_once_in_next_prompt(tmp_path):
    """A failed action's error must appear in the *next* iteration's prompt,
    then not linger into the one after that.

    Regression test for the gap found while auditing why the local model kept
    failing to click/navigate: `_last_action_error` was captured but never
    read back into `_build_iteration_prompt`, so the model got no feedback
    about why its previous choice failed and would often repeat it blind.
    """
    from src.generators.prd_generator import SimplePRDGenerator

    scraper = StubScraper()
    gen = SimplePRDGenerator(
        JsonRecordingAgent([]), scraper, progress_file=str(tmp_path / "progress.md")
    )
    gen.base_domain = "stub.example"
    state = PageState(url="https://stub.example", title="Stub", components=[], links=[])

    # No failure yet - no note in the prompt.
    assert "Note: your last action" not in gen._build_iteration_prompt(state)

    # Simulate iteration N's failure (as _execute_loop would record it).
    gen._last_action_error = "element is not visible"
    gen._last_failed_action = "click 3"

    prompt_after_failure = gen._build_iteration_prompt(state)
    assert "Note: your last action (click 3) failed: element is not visible" in prompt_after_failure

    # Consumed once - the next prompt must not repeat it.
    prompt_after_that = gen._build_iteration_prompt(state)
    assert "Note: your last action" not in prompt_after_that


def test_scraper_fill_and_submit_default_to_not_implemented():
    """Scraper.fill/submit are concrete-with-default (not abstract), so minimal
    Scraper subclasses (like the test stubs above) keep working without
    implementing them - but calling them must fail loudly, not silently no-op."""
    scraper = StubScraper()
    try:
        scraper.fill("input", "hi")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
    try:
        scraper.submit("input")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


def test_playwright_scraper_fill_and_submit(tmp_path):
    """fill() must set an input's value and submit() must trigger the form via Enter."""
    from src.scrapers.playwright_scraper import PlaywrightScraper

    fixture = tmp_path / "index.html"
    fixture.write_text(
        "<html><body>"
        '<form onsubmit="document.title=\'submitted\'; return false;">'
        '<input id="q" type="search" placeholder="Search...">'
        "</form></body></html>",
        encoding="utf-8",
    )

    scraper = PlaywrightScraper(headless=True, wait_seconds=0)
    try:
        state = scraper.navigate(fixture.as_uri())
        comp = next(c for c in state.components if c["tag"] == "input")
        assert comp["input_type"] == "search"
        assert comp["placeholder"] == "Search..."

        state = scraper.fill(comp["path"], "hello world")
        state = scraper.submit(comp["path"])
        assert state.title == "submitted"
    finally:
        scraper.close()


def test_local_agent_falls_back_when_native_tool_calling_unsupported(monkeypatch):
    """If the local server rejects the `tools` param, LocalAgent.act() must fall
    back to the text-protocol default (Agent.act()) instead of raising - and
    must not retry the native path on the next call within the same run."""
    from src.agents.local_agent import LocalAgent

    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        if "tools" in json:
            return FakeResponse(400, {"error": "tools not supported"})
        return FakeResponse(200, {"choices": [{"message": {"content": '{"action": "finish"}'}}]})

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    agent = LocalAgent(base_url="http://fake/v1/chat/completions")
    action = agent.act("prompt", system_instruction="skill text")
    assert action.kind == "finish"
    assert agent._tools_supported is False
    assert len(calls) == 2  # one failed native attempt, one text-protocol fallback

    # Second call must skip the native attempt entirely (cached False).
    action = agent.act("prompt2", system_instruction="skill text")
    assert action.kind == "finish"
    assert len(calls) == 3  # only the fallback call, no repeated native attempt


def test_local_agent_uses_native_tool_call_when_supported(monkeypatch):
    """When the server returns a real tool_calls response, LocalAgent must use it directly."""
    from src.agents.local_agent import LocalAgent

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json, headers, timeout):
        assert "tools" in json
        return FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "click",
                                        "arguments": '{"ref": 4}',
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    agent = LocalAgent(base_url="http://fake/v1/chat/completions")
    action = agent.act("prompt", system_instruction="skill text")
    assert action == AgentAction(
        kind="click", ref=4, url=None, value=None, raw='{"action": "click", "ref": 4}'
    )
    assert agent._tools_supported is True


def test_local_agent_sends_bearer_token_when_api_key_configured(monkeypatch):
    """A tunneled endpoint (e.g. LM Studio behind Tailscale) needs bearer auth;
    a bare local endpoint (no api_key configured) must not send the header."""
    from src.agents.local_agent import LocalAgent

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    seen_headers = []

    def fake_post(url, json, headers, timeout):
        seen_headers.append(headers)
        return FakeResponse(200, {"choices": [{"message": {"content": '{"action": "finish"}'}}]})

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    with_key = LocalAgent(base_url="http://fake/v1/chat/completions", api_key="sk-lm-test:token")
    with_key.generate("prompt")
    assert seen_headers[-1]["Authorization"] == "Bearer sk-lm-test:token"

    # Explicit, not incidental: LocalAgent(api_key=None) falls back to
    # LocalConfig.from_env()'s LOCAL_API_KEY, and conftest.py loads the repo's
    # real .env for the whole test session (see its docstring) - a developer
    # with a real key configured there would otherwise silently leak it into
    # this "no key configured" scenario and mask what this assertion is
    # actually meant to guard.
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    without_key = LocalAgent(base_url="http://fake/v1/chat/completions")
    without_key.generate("prompt")
    assert "Authorization" not in seen_headers[-1]


def test_local_agent_max_tokens_is_opt_in(monkeypatch):
    """max_tokens must be omitted from the request payload by default (a local
    reasoning model needs room for its own chain-of-thought - guessing a "safe"
    cap risks silently truncating it mid-thought), but included, on both the
    native tool-calling and text-fallback paths, once explicitly configured."""
    from src.agents.local_agent import LocalAgent

    monkeypatch.delenv("LOCAL_MAX_TOKENS", raising=False)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    seen_payloads = []

    def fake_post(url, json, headers, timeout):
        seen_payloads.append(json)
        return FakeResponse(200, {"choices": [{"message": {"content": '{"action": "finish"}'}}]})

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    no_cap = LocalAgent(base_url="http://fake/v1/chat/completions")
    no_cap.generate("prompt")
    assert "max_tokens" not in seen_payloads[-1]

    capped = LocalAgent(base_url="http://fake/v1/chat/completions", max_tokens=512)
    capped.generate("prompt")
    assert seen_payloads[-1]["max_tokens"] == 512

    # Native tool-calling path too - both request builders must respect it.
    capped._act_native("prompt", tools=[], system_instruction=None)
    assert seen_payloads[-1]["max_tokens"] == 512


def test_local_agent_raises_clear_error_when_truncated_by_max_tokens(monkeypatch):
    """A response cut off by max_tokens (finish_reason: 'length') must raise a
    specific, actionable error - not silently return/parse as empty content,
    which downstream every other code path would treat as an ordinary
    malformed response and just skip, with no indication of the real cause.

    Regression test: a reasoning model (DeepSeek-R1) given too small a
    max_tokens spent its entire budget on chain-of-thought, returning empty
    `content` with no `tool_calls` either - indistinguishable, before this
    fix, from any other malformed response, silently skipped every single
    iteration of a run with no way to tell max_tokens was the actual cause.
    """
    from src.agents.local_agent import LocalAgent

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json, headers, timeout):
        return FakeResponse(
            200,
            {"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
        )

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    agent = LocalAgent(base_url="http://fake/v1/chat/completions", max_tokens=64)
    try:
        agent.generate("prompt")
        assert False, "expected a RuntimeError"
    except RuntimeError as exc:
        assert "max_tokens" in str(exc)
        assert "length" in str(exc)

    # Same detection on the native tool-calling path.
    try:
        agent._act_native("prompt", tools=[], system_instruction=None)
        assert False, "expected a RuntimeError"
    except RuntimeError as exc:
        assert "max_tokens" in str(exc)


def test_local_agent_normal_finish_reason_is_unaffected(monkeypatch):
    """A normal ('stop') completion must parse exactly as before - the
    truncation check must not false-positive on ordinary responses."""
    from src.agents.local_agent import LocalAgent

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json, headers, timeout):
        return FakeResponse(
            200,
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"action": "finish"}'}}]},
        )

    monkeypatch.setattr("src.agents.local_agent.requests.post", fake_post)

    agent = LocalAgent(base_url="http://fake/v1/chat/completions")
    assert agent.generate("prompt") == '{"action": "finish"}'
