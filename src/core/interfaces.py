"""
Core interfaces and data contracts for the Pragma micro-kernel.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PageState:
    """Normalized snapshot of a scraped page (the Scraper -> Generator contract)."""

    url: str
    title: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    components: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    # Short (~300 char) description of what this page is about - meta
    # description if the site has one, else heading + first substantial
    # paragraph. "" for scrapers/tests that don't extract it. See
    # PlaywrightScraper._extract_description for how this is built and
    # SimplePRDGenerator's _record_description for how it ends up in the
    # final PRD, not just the live iteration prompt.
    description: str = ""


@dataclass
class Action:
    """A parsed agent decision."""

    kind: str
    target: str = ""


def parse_action(text: str) -> Action:
    """Parse the agent's raw decision text into an Action.

    Args:
        text: Raw agent output, expected to start with GOTO, CLICK, or FINISH.

    Returns:
        An Action with kind one of "goto", "click", "finish", "unknown".
    """
    decision = (text or "").strip()
    if decision.upper().startswith("FINISH"):
        return Action("finish")
    if decision.upper().startswith("GOTO"):
        return Action("goto", decision[4:].strip())
    if decision.upper().startswith("CLICK"):
        return Action("click", decision[5:].strip())
    if decision.upper().startswith("FILL"):
        return Action("fill", decision[4:].strip())
    if decision.upper().startswith("SUBMIT"):
        return Action("submit", decision[6:].strip())
    return Action("unknown", decision)


@dataclass
class AgentAction:
    """A parsed, backend-agnostic agent decision - the successor to `Action`.

    Produced by `Agent.act()` regardless of whether the underlying backend used
    native tool-calling or the text-based fallback, so `SimplePRDGenerator`
    never has to know which one happened. `ref` is always a numbered-list
    index into the last shown "Clickable elements" list, never a raw
    selector - resolving ref -> selector stays the generator's job (see
    `_resolve_click_selector`/`_dna_index_map` in prd_generator.py), same as
    the legacy `CLICK <number>` protocol.
    """

    kind: str  # "navigate" | "click" | "fill" | "submit" | "finish" | "help" | "unknown"
    ref: Optional[int] = None
    url: Optional[str] = None
    value: Optional[str] = None  # also carries `help`'s topic string - see parse_agent_action
    raw: str = ""


# Canonical tool surface offered to every agent backend, kept intentionally
# terse (one line each) per wiki/local-and-small-model-constraints.md - a
# small/local model pays for every token of tool-schema prose on every single
# turn, so verbose per-parameter descriptions are a real, recurring cost, not
# a one-time one. `LocalAgent` translates this list into an OpenAI-style
# `tools` payload for native function-calling; the base `Agent.act()` default
# instead renders it as a short text block appended to the system prompt.
TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "navigate",
        "description": "Go to one of the Pending routes shown to you.",
        "parameters": {"url": "string - one of the Pending routes shown"},
    },
    {
        "name": "click",
        "description": "Click a numbered element from the Clickable elements list.",
        "parameters": {"ref": "integer - the element's number"},
    },
    {
        "name": "fill",
        "description": "Type text into a numbered input/textarea element.",
        "parameters": {"ref": "integer - the element's number", "value": "string - text to enter"},
    },
    {
        "name": "submit",
        "description": "Press Enter on a numbered element to submit its form (use after fill).",
        "parameters": {"ref": "integer - the element's number"},
    },
    {
        "name": "finish",
        "description": "Conclude research once all pending routes are explored.",
        "parameters": {},
    },
    {
        "name": "help",
        "description": "Ask for guidance on a specific topic when unsure how to proceed.",
        "parameters": {
            "topic": (
                "string - one of: goal_overview, ref_semantics, navigate_usage, "
                "click_usage, fill_submit_flow, text_field_values, combobox_usage, "
                "form_completion_flow, finish_criteria"
            )
        },
    },
]

# The `help` topic enum above must stay a subset of what Module 3 actually serves at
# /static/{topic} (src/api_server/static_docs.py's TOPICS) - kept as a literal list here rather
# than importing from api_server, since core/interfaces.py must not depend on a leaf module.
# tests/test_api_server.py's drift guard checks the two stay in sync.
HELP_TOPICS: List[str] = [
    "goal_overview",
    "ref_semantics",
    "navigate_usage",
    "click_usage",
    "fill_submit_flow",
    "text_field_values",
    "combobox_usage",
    "form_completion_flow",
    "finish_criteria",
]


def _tool_block_text(tools: List[Dict[str, Any]]) -> str:
    """Render `tools` as a compact text block for backends without native tool-calling.

    One line per tool, e.g. `- click(ref): Click a numbered element...` - not a
    full JSON schema dump, to keep this cheap on every turn for small models.

    This only lists parameter *names* (`topic`), never their descriptions - a
    real model hallucinated a help topic ("navigation") that was never valid
    (`navigate_usage` is), because the only place its actual valid values ever
    appeared was inside a parameter description string this function never
    renders at all in the text-fallback path. `HELP_TOPICS` gets its own
    explicit, always-rendered line for exactly this reason - not left as prose
    buried in one tool's description that may or may not reach the model
    depending on which backend/path is active.
    """
    lines = ["Available actions:"]
    for tool in tools:
        params = ", ".join(tool["parameters"].keys())
        lines.append(f"- {tool['name']}({params}): {tool['description']}")
    if any(tool["name"] == "help" for tool in tools):
        lines.append(f"Valid help topics (must match exactly): {', '.join(HELP_TOPICS)}")
    lines.append(
        "Respond with EXACTLY ONE JSON object on a single line, e.g. "
        '{"action": "click", "ref": 3} or {"action": "fill", "ref": 2, "value": "hello"} '
        'or {"action": "navigate", "url": "example.com/about"} or {"action": "finish"}. '
        "No explanations, no markdown, no text before or after the JSON object."
    )
    return "\n".join(lines)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_agent_action(text: str) -> AgentAction:
    """Parse a model reply into an AgentAction.

    Tries the preferred single-JSON-object format first (e.g.
    `{"action": "click", "ref": 3}`), then falls back to the legacy
    GOTO/CLICK/FILL/SUBMIT/FINISH single-line text grammar (`parse_action`)
    for backends/models that don't follow the JSON format - this keeps the
    old protocol working as a safety net rather than a hard requirement.
    """
    raw = (text or "").strip()
    match = _JSON_OBJECT_RE.search(raw)
    if match:
        try:
            obj = json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError):
            obj = None
        if isinstance(obj, dict) and "action" in obj:
            kind = str(obj.get("action", "")).strip().lower()
            kind = {"goto": "navigate"}.get(kind, kind)
            if kind in ("navigate", "click", "fill", "submit", "finish", "help"):
                ref = obj.get("ref")
                try:
                    ref = int(ref) if ref is not None else None
                except (TypeError, ValueError):
                    ref = None
                # help's parameter is named "topic" in TOOL_SPECS (clearer to the model than
                # "value"), but AgentAction has no dedicated field for it - reuse `value`
                # (already fill's text-to-type field) rather than growing the dataclass for
                # one more kind. Accept either key so a model that echoes TOOL_SPECS' own
                # parameter name still parses correctly.
                value = obj.get("value")
                if kind == "help" and value is None:
                    value = obj.get("topic")
                return AgentAction(
                    kind=kind,
                    ref=ref,
                    url=obj.get("url"),
                    value=value,
                    raw=raw,
                )

    legacy = parse_action(raw)
    if legacy.kind == "goto":
        return AgentAction(kind="navigate", url=legacy.target, raw=raw)
    if legacy.kind in ("click", "fill", "submit"):
        target = legacy.target.strip()
        if legacy.kind == "fill":
            # Legacy text form: `FILL <ref> <value>`.
            parts = target.split(None, 1)
            ref_text, value = (parts[0], parts[1]) if len(parts) == 2 else (target, "")
        else:
            ref_text, value = target, None
        try:
            ref = int(ref_text)
        except ValueError:
            ref = None
        return AgentAction(kind=legacy.kind, ref=ref, value=value, raw=raw)
    if legacy.kind == "finish":
        return AgentAction(kind="finish", raw=raw)
    return AgentAction(kind="unknown", raw=raw)


class Scraper(ABC):
    """Interface for web scrapers."""

    @abstractmethod
    def navigate(self, url: str) -> PageState:
        """Navigate to a URL and return the page state.

        Args:
            url: The target URL to navigate to.

        Returns:
            A PageState describing the resulting page.
        """
        raise NotImplementedError

    @abstractmethod
    def click(self, selector: str) -> PageState:
        """Click an element and return the new page state.

        Args:
            selector: CSS selector or text description of the element.

        Returns:
            A PageState describing the resulting page.
        """
        raise NotImplementedError

    @abstractmethod
    def get_state(self) -> PageState:
        """Return the current state of the page.

        Returns:
            A PageState describing the current page.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the browser session and clean up resources."""
        raise NotImplementedError

    def fill(self, selector: str, value: str) -> PageState:
        """Type `value` into an input/textarea element and return the new page state.

        Concrete (not abstract) with a NotImplementedError default rather than
        an abstract method, so existing minimal Scraper implementations (test
        stubs, alternate backends) keep working unchanged unless they
        specifically opt into supporting fill - only PlaywrightScraper
        overrides this today.

        Args:
            selector: CSS selector identifying the target element.
            value: Text to enter into the element.

        Returns:
            A PageState describing the resulting page.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support fill()")

    def submit(self, selector: str) -> PageState:
        """Press Enter on an element (e.g. after fill) and return the new page state.

        Concrete-with-default for the same reason as `fill` above.

        Args:
            selector: CSS selector identifying the target element.

        Returns:
            A PageState describing the resulting page.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support submit()")


class Agent(ABC):
    """Interface for AI agent backends."""

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Return text generated by an LLM or agent backend.

        Args:
            prompt: The user prompt to process.
            system_instruction: Optional system-level instructions or persona.

        Returns:
            The generated response text.
        """
        raise NotImplementedError

    def act(
        self,
        prompt: str,
        tools: List[Dict[str, Any]] = TOOL_SPECS,
        system_instruction: Optional[str] = None,
    ) -> AgentAction:
        """Return a structured AgentAction decision, using `tools` as the action surface.

        Default (concrete) implementation: any backend gets this for free just
        by implementing `generate()` - it appends a compact text description
        of `tools` to the system prompt (see `_tool_block_text`) and parses
        the reply as either a single JSON action object or the legacy
        GOTO/CLICK/FILL/SUBMIT/FINISH text grammar (see `parse_agent_action`).

        A backend whose server/model supports real function-calling (e.g.
        LocalAgent talking to an OpenAI-compatible endpoint with the `tools`
        request param) should override this to attempt that first, falling
        back to `super().act(...)` when the model/server doesn't cooperate -
        see LocalAgent.act() for the pattern.
        """
        combined = f"{system_instruction}\n\n{_tool_block_text(tools)}" if system_instruction else _tool_block_text(tools)
        reply = self.generate(prompt, system_instruction=combined)
        return parse_agent_action(reply)


class GraphStore(ABC):
    """Interface for the crawl graph's persistence/query backend.

    Every method is scoped by `site` (the crawled domain) so multiple sites
    can be tracked side by side without their data mixing - the tool is
    expected to crawl many different websites over time, each analyzed
    independently. `url` values passed in and returned are always the
    already-normalized, scheme-stripped node key (see `_clean_url` in
    SimplePRDGenerator) - the store itself does not re-normalize.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection and idempotently ensure schema exists."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release the connection. Safe to call even if never connected."""
        raise NotImplementedError

    @abstractmethod
    def upsert_page(
        self,
        site: str,
        url: str,
        status: str = "Pending",
        components: int = 0,
        context: str = "",
        label: str = "",
    ) -> None:
        """Create or update a page node for `site`.

        A bare rediscovery (status="Pending") must never clobber an already
        Finished page's recorded status/components, mirroring the old
        `_add_route` behavior - only a non-Pending status overwrites.
        """
        raise NotImplementedError

    @abstractmethod
    def is_visited(self, site: str, url: str) -> bool:
        """Whether this page is a Finished node in the graph for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_pending(self, site: str, limit: Optional[int] = None) -> List[str]:
        """Up to `limit` Pending page urls for `site`, sorted ascending. Unbounded if limit is None."""
        raise NotImplementedError

    @abstractmethod
    def get_page_label(self, site: str, url: str) -> Optional[str]:
        """The link-text label recorded for a page, if any."""
        raise NotImplementedError

    @abstractmethod
    def record_link(self, site: str, from_url: str, to_url: str, label: str) -> None:
        """Record that a link from `from_url` to `to_url` was discovered, with its visible text.

        Distinct from `record_edge` (an actually-taken navigation): this
        captures every discovered link association per source page, so a
        later GOTO's component description can be verified against the
        specific page it claims to have come from. A single page can be
        linked to from many different source pages with different anchor
        text - collapsing that into one label per destination page (rather
        than one per from/to pair) previously caused a GOTO's reported
        component to describe a link that exists on some other page
        entirely, not the page actually being navigated from.
        """
        raise NotImplementedError

    @abstractmethod
    def get_link_label(self, site: str, from_url: str, to_url: str) -> Optional[str]:
        """The label of a specific from->to link discovery, if one was ever recorded."""
        raise NotImplementedError

    @abstractmethod
    def record_edge(self, site: str, from_url: str, to_url: str, component: str, action: str) -> None:
        """Record a successful navigation from `from_url` to `to_url` for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_edges(self, site: str) -> List[Dict[str, str]]:
        """All recorded edges for `site`, each {"from", "component", "action", "to"}, in insertion order."""
        raise NotImplementedError

    @abstractmethod
    def get_progress_table_rows(self, site: str) -> List[Dict[str, Any]]:
        """All page rows for `site` as {"url", "status", "components", "label"},

        sorted by (status != "Finished", url) ascending.
        """
        raise NotImplementedError

    @abstractmethod
    def count_visited(self, site: str) -> Tuple[int, int]:
        """(finished_count, total_count) of pages tracked for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_loop_signals(self, site: str, url: str) -> List[Dict[str, str]]:
        """Distinct {"component", "from"} pairs of edges already leading into `url` for `site`.

        Empty if `url` has never been reached before. Used to warn the agent
        that a page it's about to land on has already been reached via one or
        more other components, without hard-blocking the action.
        """
        raise NotImplementedError

    @abstractmethod
    def clear_site(self, site: str) -> None:
        """Delete every page/edge/link/component tracked for `site`, leaving other sites untouched.

        For a backend that persists across runs (Neo4j), this is what actually
        resets state between crawls - `Engine.from_config` calls it by default
        (`PragmaConfig.fresh`) before wiring the generator. Without it, a site
        whose URLs are per-session tokens (e.g. a `/o/<random-id>` order flow)
        silently accumulates a "visited" node for every past run's session,
        forever - none of which will ever be seen again, but all of which the
        next run's plan/synthesis steps still read back as real history. A
        process-local store (InMemoryGraphStore) never persists across runs
        regardless, so this is a no-op there - implemented uniformly anyway so
        callers stay backend-agnostic.
        """
        raise NotImplementedError

    # -- Component-level frontier -------------------------------------------------
    # A Page node tracks whether a page was ever visited; these methods track the
    # finer-grained question of whether an individual interactive element on that
    # page was ever acted on. Without this, a component's "have I touched this"
    # state either lives only in the calling process's memory (lost the moment the
    # agent navigates away, and never present at all on turn one of a later run
    # against the same persisted site) or isn't tracked at all. `page_url` here is
    # always the already-`_clean_url`-canonicalized page key (see SimplePRDGenerator),
    # exactly like every `url` elsewhere in this interface; `path` is the CSS
    # selector the scraper itself produces for the element (its `gp()` helper),
    # reused as-is rather than inventing a second identity scheme.

    @abstractmethod
    def record_component(
        self,
        site: str,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        role: str = "",
        input_type: str = "",
        visible: bool = True,
        layer: str = "semantic",
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
        component_type: str = "",
    ) -> None:
        """Create or refresh a Component node for `site`/`page_url`/`path`.

        Idempotent, same discipline as `upsert_page`: descriptive fields
        (tag/text/role/input_type/visible/layer/x/y/width/height/component_type)
        refresh on every call since they can legitimately change page to page
        (e.g. text, or a layout shift moving an element) - but `interacted`,
        its interaction history, and `options` (see `record_component_options`)
        are never touched here - only their own dedicated setters do, and a
        rediscovery must never clobber state that isn't recomputed every call.

        `x`/`y`/`width`/`height` are the element's viewport-relative bounding
        box in CSS pixels at the moment it was discovered (see
        PlaywrightScraper._discover_components), `None` when unknown (e.g. a
        scraper/test double that doesn't report it). This is what makes the
        stored checklist a *precise* map of the page - not just "this exists
        somewhere" but "this exists right here" - useful for a human auditing
        the checklist, and a documented building block for coordinate-based
        interaction, though `click`/`fill`/`submit` still resolve by selector
        today, not by position.

        `component_type` is a short, deterministic classification (see
        `src.generators.component_classifier.classify_component_type`) - e.g.
        "checkbox", "text field (email)", "combobox (searchable dropdown)" -
        computed from tag/role/input_type alone, safe to recompute and
        overwrite every call like the other descriptive fields.
        """
        raise NotImplementedError

    @abstractmethod
    def record_component_options(
        self, site: str, page_url: str, path: str, options: str, excluded_from_debt: bool = False
    ) -> None:
        """Set (fully overwrite) the JSON-encoded `options` field on a Component
        node - structured facts beyond simple existence: a revealed dropdown's
        choices and which one is selected, a stepper's paired increment/
        decrement paths and current value, or a radio/checkbox group's
        sibling members. See `component_classifier.py` for what actually
        computes these; this method only persists whatever JSON string it's
        given, keyed the same way as `record_component`.

        Deliberately a *separate* method from `record_component`, not one more
        parameter on it: `options` is really only knowable at specific moments
        (e.g. right after a click reveals a dropdown's items - a before/after
        diff, not something present in any single discovery snapshot), unlike
        every field `record_component` refreshes, which is recomputable from
        the current DOM alone on every single call. Folding `options` into
        that same call would mean every ordinary rediscovery (most of which
        have no idea what a component's options are) would overwrite it back
        to empty, permanently erasing something more expensive to learn than
        to lose.

        Auto-creates the Component node if it doesn't already exist, mirroring
        `record_component_interaction`'s auto-create (a caller with options to
        record for a path it hasn't explicitly `record_component`-ed yet
        should still succeed, not silently no-op).

        `excluded_from_debt`: marks this component as a *grouped member* that
        should never itself count toward "unexplored debt" (see
        `count_unexplored_components`/`get_pages_with_unexplored_components`/
        `page_has_unexplored_components` below) - the fix for a revealed
        dropdown/combobox's option set: each option (e.g. one of a dozen
        empanada flavors) is still discovered and still gets its own Component
        node (so it's listable, clickable, and shows up in the ledger/catalog
        for a human to audit), but only the *trigger* that revealed them is
        required to have been interacted with to satisfy the completion guard
        - not every individual option. Without this, a page with N revealed
        options needed all N clicked before `finish` was allowed, in addition
        to the trigger itself, which is both wasteful and not what "explored
        this selector" should mean. Defaults to `False` so every existing
        caller (steppers, radio/checkbox groups) keeps its current, unchanged
        behavior - those groups' members still individually count as debt,
        which is intentionally out of scope for this flag for now (see
        docs/explicativos/pendientes-futuras-fases.md).
        """
        raise NotImplementedError

    @abstractmethod
    def record_component_interaction(
        self,
        site: str,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
    ) -> None:
        """Mark a component as interacted with and append one interaction record.

        Auto-creates the Component node if it doesn't already exist (mirrors
        `record_edge`'s auto-create of its endpoint Page nodes) - an
        interaction can be recorded even if `record_component` wasn't called
        first in some code path.
        """
        raise NotImplementedError

    @abstractmethod
    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        """All known components for one page:
        {path: {tag, text, interacted, visible, x, y, width, height,
        component_type, options}}.

        One query per prompt build, not one per component - the caller is
        expected to build this once per iteration and read from the dict
        repeatedly for the same page. `x`/`y`/`width`/`height` are `None` for
        components recorded before position tracking existed, or by a
        scraper/test double that doesn't report it. `options` is the raw JSON
        string set by `record_component_options`, `""` if never set - callers
        that need the structured value should `json.loads` it themselves.
        """
        raise NotImplementedError

    @abstractmethod
    def count_unexplored_components(self, site: str, semantic_only: bool = True) -> Tuple[int, int]:
        """(unexplored_count, total_count) of components tracked across all of `site`.

        `semantic_only=True` excludes `layer="pointer"` components (the
        cursor:pointer catch-all, capped and noisier than the semantic/ARIA
        selector) from both counts, so a completion guard reading this isn't
        gated by the least reliable discovery layer.
        """
        raise NotImplementedError

    @abstractmethod
    def get_pages_with_unexplored_components(
        self, site: str, limit: Optional[int] = None, semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        """[{"url", "unexplored_count"}] for pages with >=1 unexplored component, sorted descending.

        This is the revisit queue: pages the agent has already left behind
        that still have real, undone work on them.
        """
        raise NotImplementedError

    @abstractmethod
    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        """Whether `url` has at least one un-interacted-with component tracked.

        The condition under which a revisit to an already-visited page is not
        redundant - used to relax the navigate-decline guard without turning
        it into an override (the guard still only ever declines, just with a
        more accurate redundancy condition).
        """
        raise NotImplementedError

    @abstractmethod
    def get_component_ledger(self, site: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """{page_url: {path: {tag, text, interacted, interactions, x, y, width,
        height, component_type, options}}} for all of `site`.

        The durable, human-inspectable "what did I do on this page, and to
        what" record - what `_write_component_ledger` writes out, sourced from
        real persisted state rather than a parallel in-memory shadow copy.
        """
        raise NotImplementedError


class PRDGenerator(ABC):
    """Interface for PRD generation orchestration strategies."""

    @abstractmethod
    def generate_prd(self, url: str) -> str:
        """Orchestrate the agent to explore the URL and generate a PRD.

        Args:
            url: The starting URL for exploration.

        Returns:
            The final PRD in Markdown format.
        """
        raise NotImplementedError
