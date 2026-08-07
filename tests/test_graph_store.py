"""Tests for the GraphStore abstraction - in-memory (always run) and Neo4j (opt-in)."""
from src.storage.memory_graph_store import InMemoryGraphStore


def test_memory_store_upsert_is_idempotent_per_site():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "a.com/x", status="Pending", components=0)
    store.upsert_page("a.com", "a.com/x", status="Finished", components=5)
    # A later bare rediscovery must not clobber the Finished status/components.
    store.upsert_page("a.com", "a.com/x", status="Pending", components=0)

    rows = store.get_progress_table_rows("a.com")
    assert len(rows) == 1
    assert rows[0]["status"] == "Finished"
    assert rows[0]["components"] == 5


def test_memory_store_is_visited_false_for_unknown_url():
    store = InMemoryGraphStore()
    assert store.is_visited("a.com", "a.com/never-seen") is False


def test_memory_store_pending_respects_limit_and_order():
    store = InMemoryGraphStore()
    for i in (3, 1, 2):
        store.upsert_page("a.com", f"a.com/page-{i}")

    assert store.get_pending("a.com") == ["a.com/page-1", "a.com/page-2", "a.com/page-3"]
    assert store.get_pending("a.com", limit=2) == ["a.com/page-1", "a.com/page-2"]


def test_memory_store_site_isolation():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "shared/path", status="Pending")
    store.upsert_page("b.com", "shared/path", status="Finished")

    assert store.is_visited("a.com", "shared/path") is False
    assert store.is_visited("b.com", "shared/path") is True
    assert store.get_pending("a.com") == ["shared/path"]
    assert store.get_pending("b.com") == []

    store.record_edge("a.com", "a.com/home", "a.com/about", "link", "GOTO a.com/about")
    store.record_edge("b.com", "b.com/home", "b.com/about", "link", "GOTO b.com/about")
    assert len(store.get_edges("a.com")) == 1
    assert len(store.get_edges("b.com")) == 1
    assert store.get_edges("a.com")[0]["to"] == "a.com/about"
    assert store.get_edges("b.com")[0]["to"] == "b.com/about"


def test_memory_store_link_label_is_scoped_to_the_specific_from_to_pair():
    store = InMemoryGraphStore()
    store.record_link("a.com", "a.com/home", "a.com/about", "About Us")
    store.record_link("a.com", "a.com/other-page", "a.com/about", "Learn more")

    assert store.get_link_label("a.com", "a.com/home", "a.com/about") == "About Us"
    assert store.get_link_label("a.com", "a.com/other-page", "a.com/about") == "Learn more"
    # No link was ever recorded from this page to /about - must not fall back
    # to any label discovered via a different source page.
    assert store.get_link_label("a.com", "a.com/unrelated-page", "a.com/about") is None


def test_memory_store_loop_signals_detects_revisit():
    store = InMemoryGraphStore()
    store.record_edge("a.com", "a.com/home", "a.com/contact", "link \"Contact\"", "GOTO a.com/contact")
    store.record_edge("a.com", "a.com/about", "a.com/contact", "link \"Contact us\"", "GOTO a.com/contact")

    signals = store.get_loop_signals("a.com", "a.com/contact")
    assert len(signals) == 2
    assert {"component": 'link "Contact"', "from": "a.com/home"} in signals

    assert store.get_loop_signals("a.com", "a.com/never-reached") == []


def test_memory_store_clear_site_removes_only_that_site():
    store = InMemoryGraphStore()
    store.upsert_page("a.com", "a.com/x", status="Finished")
    store.record_edge("a.com", "a.com/home", "a.com/x", "link", "GOTO a.com/x")
    store.upsert_page("b.com", "b.com/x", status="Finished")

    store.clear_site("a.com")

    assert store.get_progress_table_rows("a.com") == []
    assert store.get_edges("a.com") == []
    # Untouched: clear_site is scoped to the one site, not a global reset.
    assert store.is_visited("b.com", "b.com/x") is True


def test_memory_store_record_component_is_idempotent_and_preserves_interacted():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#go", tag="button", text="Go")
    store.record_component_interaction("a.com", "a.com/x", "button#go", action="click")
    # A later rediscovery (e.g. the page is revisited) must not clobber the
    # interacted flag or its interaction history - only descriptive fields
    # (tag/text/etc.) refresh, same discipline as upsert_page's Pending-never-
    # clobbers-Finished rule.
    store.record_component("a.com", "a.com/x", "button#go", tag="button", text="Go (updated)")

    states = store.get_component_states("a.com", "a.com/x")
    assert states["button#go"]["interacted"] is True
    assert states["button#go"]["text"] == "Go (updated)"


def test_memory_store_record_component_persists_position():
    store = InMemoryGraphStore()
    store.record_component(
        "a.com", "a.com/x", "button#go", tag="button", text="Go",
        x=10.0, y=20.0, width=80.0, height=32.0,
    )
    states = store.get_component_states("a.com", "a.com/x")
    assert states["button#go"]["x"] == 10.0
    assert states["button#go"]["y"] == 20.0
    assert states["button#go"]["width"] == 80.0
    assert states["button#go"]["height"] == 32.0

    ledger = store.get_component_ledger("a.com")
    assert ledger["a.com/x"]["button#go"]["width"] == 80.0

    # A component recorded by a caller that doesn't know position (e.g. a test
    # double, or record_component_interaction's auto-create) must not error -
    # position is just None, not a required field.
    store.record_component("a.com", "a.com/y", "button#other")
    assert store.get_component_states("a.com", "a.com/y")["button#other"]["x"] is None


def test_memory_store_record_component_interaction_auto_creates_node():
    store = InMemoryGraphStore()
    store.record_component_interaction("a.com", "a.com/x", "button#go", action="click", value="", resulting_url="a.com/y")

    states = store.get_component_states("a.com", "a.com/x")
    assert states["button#go"]["interacted"] is True

    ledger = store.get_component_ledger("a.com")
    assert ledger["a.com/x"]["button#go"]["interactions"] == [
        {"action": "click", "value": "", "resulting_url": "a.com/y"}
    ]


def test_memory_store_count_unexplored_components_respects_semantic_only():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a", layer="semantic")
    store.record_component("a.com", "a.com/x", "div#b", layer="pointer")

    assert store.count_unexplored_components("a.com", semantic_only=True) == (1, 1)
    assert store.count_unexplored_components("a.com", semantic_only=False) == (2, 2)

    store.record_component_interaction("a.com", "a.com/x", "button#a", action="click")
    assert store.count_unexplored_components("a.com", semantic_only=True) == (0, 1)


def test_memory_store_page_has_unexplored_components():
    store = InMemoryGraphStore()
    assert store.page_has_unexplored_components("a.com", "a.com/x") is False

    store.record_component("a.com", "a.com/x", "button#a")
    assert store.page_has_unexplored_components("a.com", "a.com/x") is True

    store.record_component_interaction("a.com", "a.com/x", "button#a", action="click")
    assert store.page_has_unexplored_components("a.com", "a.com/x") is False


def test_memory_store_get_pages_with_unexplored_components_sorted_descending():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a")
    store.record_component("a.com", "a.com/y", "button#b")
    store.record_component("a.com", "a.com/y", "button#c")
    # Fully explored - must not appear in the debt list at all.
    store.record_component("a.com", "a.com/z", "button#d")
    store.record_component_interaction("a.com", "a.com/z", "button#d", action="click")

    rows = store.get_pages_with_unexplored_components("a.com")
    assert rows == [
        {"url": "a.com/y", "unexplored_count": 2},
        {"url": "a.com/x", "unexplored_count": 1},
    ]


def test_memory_store_excluded_from_debt_members_never_count_as_unexplored():
    """A grouped member (e.g. one of a revealed dropdown's options) tagged
    excluded_from_debt=True must never itself count toward unexplored debt,
    in any of the three debt-facing query methods - the fix for a dropdown
    with N choices otherwise requiring N individual clicks (one per choice,
    e.g. one per empanada flavor) before `finish` would be allowed, on top
    of the trigger that revealed them."""
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "div#trigger", tag="div", text="Sabor")
    store.record_component("a.com", "a.com/x", "div#opt1", tag="div", role="option", text="Jamon y queso")
    store.record_component("a.com", "a.com/x", "div#opt2", tag="div", role="option", text="Carne")
    store.record_component_options(
        "a.com", "a.com/x", "div#opt1", '{"kind": "revealed_option_member"}', excluded_from_debt=True
    )
    store.record_component_options(
        "a.com", "a.com/x", "div#opt2", '{"kind": "revealed_option_member"}', excluded_from_debt=True
    )

    # Only the trigger counts, in both numerator and denominator - the two
    # excluded options drop out of "total" too, same as the pointer layer does
    # under semantic_only, since they no longer represent tracked debt at all.
    assert store.count_unexplored_components("a.com", semantic_only=False) == (1, 1)
    assert store.get_pages_with_unexplored_components("a.com") == [
        {"url": "a.com/x", "unexplored_count": 1}
    ]
    assert store.page_has_unexplored_components("a.com", "a.com/x") is True

    # Interacting with the trigger alone (never the options) clears the page's debt.
    store.record_component_interaction("a.com", "a.com/x", "div#trigger", action="click")
    assert store.count_unexplored_components("a.com", semantic_only=False) == (0, 1)
    assert store.get_pages_with_unexplored_components("a.com") == []
    assert store.page_has_unexplored_components("a.com", "a.com/x") is False


def test_memory_store_record_component_options_preserves_excluded_from_debt_flag():
    """excluded_from_debt must survive get_component_states/get_component_ledger
    (not just the internal debt-counting queries) so a caller inspecting the
    persisted checklist can tell a grouped member apart from a standalone one."""
    store = InMemoryGraphStore()
    store.record_component_options(
        "a.com", "a.com/x", "div#opt1", '{"kind": "revealed_option_member"}', excluded_from_debt=True
    )

    assert store.get_component_states("a.com", "a.com/x")["div#opt1"]["excluded_from_debt"] is True
    assert store.get_component_ledger("a.com")["a.com/x"]["div#opt1"]["excluded_from_debt"] is True


def test_memory_store_clear_site_removes_components_too():
    store = InMemoryGraphStore()
    store.record_component("a.com", "a.com/x", "button#a")
    store.clear_site("a.com")

    assert store.get_component_states("a.com", "a.com/x") == {}
    assert store.count_unexplored_components("a.com") == (0, 0)


def test_generator_uses_injected_graph_store(tmp_path):
    from src.core.engine import Engine
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    store = InMemoryGraphStore()
    agent = ScriptedAgent(["plan", "GOTO https://stub/page-a", "FINISH"])
    scraper = StubScraper()
    gen = SimplePRDGenerator(
        agent, scraper, graph_store=store, progress_file=str(tmp_path / "progress.md"), max_iterations=3
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert store is gen.graph_store
    assert len(store.get_edges(gen.base_domain)) == 1


def test_full_page_inventory_is_recorded_with_position_beyond_the_shown_batch(tmp_path):
    """Every component discovered on a page - not just the component_batch_size-capped
    subset shown to the model that turn - must be persisted into graph_store, position
    included, the moment the page loads. This is the deterministic "special iteration"
    (_record_page_inventory): without it, a component that never wins a batch slot (e.g.
    it sits behind many higher-priority components) would never be persisted at all, and
    so could never surface as unexplored debt."""
    from src.core.engine import Engine
    from src.core.interfaces import PageState, Scraper
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent

    class ManyComponentsScraper(Scraper):
        def navigate(self, url):
            return PageState(
                url="https://stub",
                title="Stub",
                components=[
                    {
                        "tag": "button", "text": f"button {i}", "path": f"button#b{i}",
                        "rect": {"x": i * 10.0, "y": 0.0, "width": 50.0, "height": 20.0},
                    }
                    for i in range(5)
                ],
                links=[],
            )

        def click(self, selector):
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    store = InMemoryGraphStore()
    agent = ScriptedAgent(["plan", "FINISH"])
    scraper = ManyComponentsScraper()
    gen = SimplePRDGenerator(
        agent, scraper, graph_store=store, progress_file=str(tmp_path / "progress.md"),
        max_iterations=2, component_batch_size=2,  # only 2 of 5 would ever be *shown*
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    states = store.get_component_states(gen.base_domain, "stub")
    # All 5 must be persisted, not just the 2 shown to the model this turn.
    assert len(states) == 5
    assert states["button#b3"]["x"] == 30.0
    assert states["button#b3"]["width"] == 50.0


class _SpyGraphStore(InMemoryGraphStore):
    """Records clear_site calls without needing a live Neo4j instance -
    exercises Engine.from_config's PragmaConfig.fresh wiring directly."""

    def __init__(self) -> None:
        super().__init__()
        self.cleared_sites: list = []

    def clear_site(self, site: str) -> None:
        self.cleared_sites.append(site)
        super().clear_site(site)


def test_engine_from_config_clears_site_when_fresh(tmp_path):
    from src.core.config import PragmaConfig
    from src.core.engine import Engine
    from src.core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", scraper="playwright", agent="mock",
        graph_store="_spy_fresh_test", out_dir=str(tmp_path), logs_dir=str(tmp_path),
        progress_logs_dir=str(tmp_path), graph_logs_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert isinstance(engine.graph_store, _SpyGraphStore)
    assert engine.graph_store.cleared_sites == ["stub.example"]


def test_engine_from_config_skips_clear_when_not_fresh(tmp_path):
    from src.core.config import PragmaConfig
    from src.core.engine import Engine
    from src.core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_no_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", scraper="playwright", agent="mock",
        graph_store="_spy_no_fresh_test", fresh=False, out_dir=str(tmp_path), logs_dir=str(tmp_path),
        progress_logs_dir=str(tmp_path), graph_logs_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert engine.graph_store.cleared_sites == []


def test_apply_diminishing_returns_gives_up_after_no_improvement(tmp_path):
    """A page whose unexplored count stays flat (or grows) across
    max_stalled_finish_attempts consecutive checks must be excluded from the
    debt list and added to _given_up_pages - the fix for a component whose CSS
    path shifts every DOM change (e.g. a quantity stepper) never converging,
    and a real interaction (e.g. a login retry) whose outcome never changes."""
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    gen = SimplePRDGenerator(
        ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"),
        max_stalled_finish_attempts=3,
    )

    # Check 1: first time seeing this page's debt - always kept, strikes start at 0.
    result = gen._apply_diminishing_returns([{"url": "stub/x", "unexplored_count": 5}])
    assert result == [{"url": "stub/x", "unexplored_count": 5}]
    assert "stub/x" not in gen._given_up_pages

    # Checks 2-3: debt doesn't improve (stays at 5, or grows to 7) - strikes accumulate,
    # page stays in the list right up until the threshold.
    result = gen._apply_diminishing_returns([{"url": "stub/x", "unexplored_count": 5}])
    assert result == [{"url": "stub/x", "unexplored_count": 5}]
    result = gen._apply_diminishing_returns([{"url": "stub/x", "unexplored_count": 7}])
    assert result == [{"url": "stub/x", "unexplored_count": 7}]

    # Check 4: third consecutive non-improving check (5 -> 5 -> 7 -> 7, no strict decrease
    # since check 1) trips max_stalled_finish_attempts=3 - page is given up on and dropped.
    result = gen._apply_diminishing_returns([{"url": "stub/x", "unexplored_count": 7}])
    assert result == []
    assert "stub/x" in gen._given_up_pages

    # Once given up, it's excluded from every future call outright, regardless of count.
    result = gen._apply_diminishing_returns([{"url": "stub/x", "unexplored_count": 100}])
    assert result == []


def test_apply_diminishing_returns_resets_strikes_on_real_progress(tmp_path):
    """A page whose debt actually shrinks between checks must never be given
    up on, no matter how many checks happen - e.g. a filter component that
    keeps revealing new, genuinely-unexplored result components each time a
    different value is tried."""
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    gen = SimplePRDGenerator(
        ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"),
        max_stalled_finish_attempts=2,
    )

    counts = [10, 12, 9, 11, 8, 10, 7]  # noisy, but each pair of checks includes a decrease
    for count in counts:
        result = gen._apply_diminishing_returns([{"url": "stub/filters", "unexplored_count": count}])
        # Never given up on, since a strict decrease resets strikes to 0 before any
        # single non-improving check alone could reach the threshold.
        assert result == [{"url": "stub/filters", "unexplored_count": count}]
    assert "stub/filters" not in gen._given_up_pages


def test_build_page_catalog_facts_collapses_groups_into_single_entries(tmp_path):
    """A stepper's 3 members and a choice-group's N members must each collapse
    into exactly one catalog fact, not one per member - the model is asked to
    describe "the control," not each button separately (see
    component-catalog-skill's rules)."""
    import json as json_module

    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    gen = SimplePRDGenerator(ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"))

    stepper_pair = json_module.dumps({
        "paired_with": {"decrement": "button#dec", "increment": "button#inc", "value": "span#val"},
        "current_value": "3",
    })
    ledger = {
        "button#dec": {
            "tag": "button", "text": "Restar", "interacted": True,
            "component_type": "button", "options": json_module.dumps({"kind": "stepper_decrement", **json_module.loads(stepper_pair)}),
        },
        "button#inc": {
            "tag": "button", "text": "Agregar", "interacted": False,
            "component_type": "button", "options": json_module.dumps({"kind": "stepper_increment", **json_module.loads(stepper_pair)}),
        },
        "span#val": {
            "tag": "span", "text": "3", "interacted": False,
            "component_type": "element", "options": json_module.dumps({"kind": "stepper_value", **json_module.loads(stepper_pair)}),
        },
        "input#radio1": {
            "tag": "input", "text": "Small", "interacted": False, "component_type": "radio button",
            "options": json_module.dumps({
                "kind": "choice_group_member", "group_name": "size",
                "choices": [{"text": "Small", "selected": True}, {"text": "Large", "selected": False}],
            }),
        },
        "input#radio2": {
            "tag": "input", "text": "Large", "interacted": False, "component_type": "radio button",
            "options": json_module.dumps({
                "kind": "choice_group_member", "group_name": "size",
                "choices": [{"text": "Small", "selected": True}, {"text": "Large", "selected": False}],
            }),
        },
        "button#plain": {
            "tag": "button", "text": "Submit", "interacted": True, "component_type": "submit button",
            "options": "",
        },
    }

    facts = gen._build_page_catalog_facts(ledger)

    # 6 ledger entries collapse to 3 facts: one stepper, one choice group, one plain button.
    assert len(facts) == 3

    stepper_fact = next(f for f in facts if f["type"] == "stepper control (increment/decrement)")
    assert stepper_fact["current_value"] == "3"

    group_fact = next(f for f in facts if f["type"] == "radio/checkbox group")
    assert group_fact["text"] == "group 'size'"
    assert group_fact["choices"] == [{"text": "Small", "selected": True}, {"text": "Large", "selected": False}]

    plain_fact = next(f for f in facts if f["type"] == "submit button")
    assert plain_fact["interacted"] is True


def test_build_page_catalog_facts_handles_combobox_trigger():
    import json as json_module

    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmp:
        gen = SimplePRDGenerator(ScriptedAgent([]), StubScraper(), progress_file=os.path.join(tmp, "p.md"))
        ledger = {
            "div#trigger": {
                "tag": "div", "text": "Tercera Docena", "interacted": True,
                "component_type": "custom control (component-library element, no native tag/role)",
                "options": json_module.dumps({
                    "kind": "combobox_trigger",
                    "choices": [
                        {"text": "Mi Gusto", "selected": True},
                        {"text": "Solo Empanadas", "selected": False},
                    ],
                }),
            },
        }
        facts = gen._build_page_catalog_facts(ledger)
        assert len(facts) == 1
        assert facts[0]["choices"][0] == {"text": "Mi Gusto", "selected": True}


def test_build_page_catalog_facts_flags_genuinely_unlabeled_components(tmp_path):
    """A component whose `text` is still '' after the scraper's broadened
    label fallback chain (see PlaywrightScraper._discover_components) must
    read as "no accessible label found" in the fact fed to narration, not as
    plain '' - which used to be indistinguishable from a labelling bug and
    got narrated as "Unnamed Element"/"Empty Element" regardless of whether
    the element genuinely had no label."""
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent, StubScraper

    gen = SimplePRDGenerator(ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"))
    ledger = {
        "div#mystery": {
            "tag": "div", "text": "", "interacted": False,
            "component_type": "element", "options": "",
        },
    }
    facts = gen._build_page_catalog_facts(ledger)
    assert len(facts) == 1
    assert facts[0]["text"] == "(no accessible label found on this element)"
    # No CSS selector/path leaks into the fact text - the narration skill is
    # explicitly told never to surface implementation details.
    assert "#" not in facts[0]["text"]


def test_opening_a_dropdown_does_not_require_clicking_every_revealed_option(tmp_path):
    """End-to-end regression test for the empanad.app flavor-picker case: opening a
    dropdown/combobox (one click on its trigger) must be enough to satisfy
    `_reject_premature_finish` - the model must NOT be forced to individually click
    every one of the revealed options (e.g. every flavor) before `finish` succeeds."""
    from src.core.engine import Engine
    from src.core.interfaces import PageState, Scraper
    from src.generators.prd_generator import SimplePRDGenerator
    from tests.test_imports import ScriptedAgent

    class FlavorPickerScraper(Scraper):
        def navigate(self, url):
            return PageState(
                url="https://stub",
                title="Stub",
                components=[{"tag": "div", "text": "Elegir sabor", "path": "div#trigger"}],
                links=[],
            )

        def click(self, selector):
            if selector == "div#trigger":
                return PageState(
                    url="https://stub",
                    title="Stub",
                    components=[
                        {"tag": "div", "text": "Elegir sabor", "path": "div#trigger"},
                        {"tag": "div", "text": "Jamon y queso", "path": "div#opt1", "role": "option"},
                        {"tag": "div", "text": "Carne", "path": "div#opt2", "role": "option"},
                        {"tag": "div", "text": "Humita", "path": "div#opt3", "role": "option"},
                    ],
                    links=[],
                )
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    store = InMemoryGraphStore()
    agent = ScriptedAgent(["plan", "CLICK 1", "FINISH"])
    scraper = FlavorPickerScraper()
    gen = SimplePRDGenerator(
        agent, scraper, graph_store=store, progress_file=str(tmp_path / "progress.md"), max_iterations=5
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    # The run must have concluded on its first FINISH attempt, not been forced to
    # revisit and click div#opt1/opt2/opt3 individually first.
    assert store.get_pages_with_unexplored_components(gen.base_domain) == []
    states = store.get_component_states(gen.base_domain, "stub")
    assert states["div#opt1"]["excluded_from_debt"] is True
    assert states["div#trigger"]["interacted"] is True
    # The options are still fully discovered/listed, just not individually required.
    assert set(states.keys()) == {"div#trigger", "div#opt1", "div#opt2", "div#opt3"}


def test_write_component_catalog_narrates_per_page_and_persists_facts(tmp_path):
    """End-to-end: a click revealing a combobox's options must show up in the
    generated component catalog file - the concrete "Tercera Docena" example
    this feature exists for."""
    from src.core.engine import Engine
    from src.core.interfaces import Agent, PageState, Scraper, parse_agent_action
    from src.generators.prd_generator import SimplePRDGenerator

    class NarratingAgent(Agent):
        """act() follows a fixed script (like ScriptedAgent); generate() is
        used only for _create_plan/_write_component_catalog and returns a
        fixed, recognizable narration string, recording every prompt it was
        given - decouples action-parsing from narration so this test doesn't
        have to reason about a shared call counter between the two."""

        def __init__(self, script):
            self.script = list(script)
            self.calls = 0
            self.generate_prompts = []

        def act(self, prompt, tools=None, system_instruction=None):
            response = self.script[self.calls] if self.calls < len(self.script) else "FINISH"
            self.calls += 1
            return parse_agent_action(response)

        def generate(self, prompt, system_instruction=None):
            self.generate_prompts.append(prompt)
            return "**Combobox (searchable dropdown)**: lets the user pick a bakery."

    class ComboboxScraper(Scraper):
        def navigate(self, url):
            return PageState(
                url="https://stub",
                title="Stub",
                components=[{"tag": "div", "text": "Tercera Docena", "path": "div#trigger"}],
                links=[],
            )

        def click(self, selector):
            if selector == "div#trigger":
                return PageState(
                    url="https://stub",
                    title="Stub",
                    components=[
                        {"tag": "div", "text": "Tercera Docena", "path": "div#trigger"},
                        {"tag": "div", "text": "Mi Gusto", "path": "div#opt1", "role": "option", "selected": True},
                        {"tag": "div", "text": "Solo Empanadas", "path": "div#opt2", "role": "option", "selected": False},
                    ],
                    links=[],
                )
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="Stub")

        def close(self):
            pass

    agent = NarratingAgent(["CLICK 1", "CLICK 1", "FINISH"])
    scraper = ComboboxScraper()
    catalog_path = tmp_path / "catalog.md"
    gen = SimplePRDGenerator(
        agent, scraper,
        progress_file=str(tmp_path / "progress.md"),
        components_catalog_file=str(catalog_path),
        max_iterations=5,
    )
    engine = Engine(scraper, agent, gen, out_dir=str(tmp_path))
    engine.run("https://stub.example")

    assert catalog_path.exists()
    content = catalog_path.read_text(encoding="utf-8")
    assert "stub" in content
    assert "Combobox (searchable dropdown)" in content  # the model's narration made it into the file

    # The deterministic facts sent to the model must have named the real,
    # revealed options - not just "this has some options."
    catalog_prompts = [p for p in agent.generate_prompts if "choices=" in p]
    assert any("Mi Gusto" in p and "Solo Empanadas" in p for p in catalog_prompts)
