"""
PRD Generator implementation using a planned, multi-skill autonomous loop.
"""
from __future__ import annotations

import json
import pathlib
import unicodedata
from typing import List, Optional

from ..core.interfaces import AgentAction, Agent, GraphStore, PageState, PRDGenerator, Scraper
from ..core.registry import GENERATOR_REGISTRY
from ..scrapers.rest_scraper import DocsClient
from ..storage.memory_graph_store import InMemoryGraphStore
from ..utils.io import append_output, write_output
from .component_classifier import (
    classify_component_type,
    find_revealed_options,
    group_choice_sets,
    group_steppers,
)

# Note: the per-iteration decision call no longer needs its own "respond with
# exactly one line" instruction here - Agent.act() (see src/core/interfaces.py)
# appends that format instruction itself, derived from TOOL_SPECS, so it stays
# in sync with the actual action vocabulary (navigate/click/fill/submit/finish)
# instead of two places describing the same protocol independently. _create_plan
# below still never receives it, for the same reason as before: it needs to
# produce a multi-step narrative, not a single command.


@GENERATOR_REGISTRY.register("simple")
class SimplePRDGenerator(PRDGenerator):
    """Orchestrates an agent through discovery and structural synthesis."""

    def __init__(
        self,
        agent: Agent,
        scraper: Scraper,
        graph_store: Optional[GraphStore] = None,
        progress_file: str = "PROGRESS.md",
        progress_log_file: Optional[str] = None,
        graph_log_file: Optional[str] = None,
        components_log_file: Optional[str] = None,
        components_catalog_file: Optional[str] = None,
        max_iterations: int = 12,
        batch_size: int = 20,
        pending_batch_size: Optional[int] = None,
        component_batch_size: Optional[int] = None,
        allow_subdomains: bool = False,
        max_stalled_finish_attempts: int = 3,
        docs_client: Optional[DocsClient] = None,
        deep_context: bool = True,
        context_max_chars: int = 1500,
    ) -> None:
        """Initialize with brain (agent), hands (scraper), and progress tracker.

        Args:
            docs_client: Fetches Module 3's `/static/*` curated topics for the
                `help` action (see `_execute_loop`). Defaults to a `DocsClient`
                pointed at `PRAGMA_API_URL` (or its own localhost default) -
                `help` degrades to "unavailable" text rather than raising if
                Module 3 isn't running, so this works even when `scraper` is
                `playwright` rather than `rest`.
            graph_store: Where the navigation graph (pages + edges) is tracked
                and queried between iterations. Defaults to a fresh in-memory
                store (no persistence across runs) when not supplied - see
                InMemoryGraphStore vs Neo4jGraphStore in src/storage/.
            progress_file: Live status snapshot (route table), overwritten on every
                update - this is what gets fed back into the final synthesis step.
            progress_log_file: Optional append-only debug trail (one entry per
                plan/iteration/finish, in order) for understanding what the agent
                actually did/said across a run - never overwritten, never read
                back by the engine itself, purely for human debugging.
            graph_log_file: Optional path to write the navigation graph (JSON list
                of {from, component, action, to} edges) once the run finishes -
                which link/element led from which page to which page.
            components_log_file: Optional path to write the per-page component
                ledger (JSON) once the run finishes - every component ever shown
                on every visited page, whether it was interacted with, and the
                ordered list of actions taken on it (persisted in `graph_store`,
                see `_write_component_ledger`). This is Module 2's own state (ref
                numbering, interaction history) - not something Module 3 tracks
                or could serve, since it never participates in prompt-building.
            components_catalog_file: Optional path to write a human-readable
                component catalog (Markdown) once the run finishes - one
                narrated entry per component (or per stepper/choice-group,
                collapsed into a single entry), built from the same persisted
                `graph_store` data as `components_log_file` but classified
                (see `component_classifier.py`) and narrated by the model into
                short prose, rather than raw JSON. Generated once, after the
                research loop ends - not part of `max_iterations`' budget.
                Never written if left unset (default), matching every other
                optional log path here.
            batch_size: Default cap for both pending routes and DNA components sent
                per iteration prompt, used whenever `pending_batch_size`/
                `component_batch_size` aren't set explicitly. Smaller values mean
                faster, cheaper iterations at the cost of needing more of them
                (raise max_iterations to match) to work through a large site -
                useful for slow/small local models.
            pending_batch_size: Max pending routes shown per prompt. Falls back
                to `batch_size` if unset. Kept independent from
                `component_batch_size` because the two budgets are genuinely
                unrelated - a component-dense page (a mega-nav with hundreds of
                elements) shouldn't have to compete with a route-heavy site's
                pending-page queue for the same shared number.
            component_batch_size: Max DNA components shown per prompt. Falls
                back to `batch_size` if unset - see `pending_batch_size`.
            allow_subdomains: If true, a link to a subdomain of the crawled
                site (e.g. blog.example.com while crawling example.com) counts
                as in-scope and gets queued as a pending route too. Off by
                default - see `_domain_in_scope`.
            max_stalled_finish_attempts: How many consecutive times a page's
                unexplored-component debt can fail to improve before
                `_reject_premature_finish` gives up on that page and stops
                treating its remaining debt as blocking. Protects against two
                real failure modes: a component whose CSS path shifts every
                time a sibling is added/removed (e.g. a quantity stepper),
                which never accumulates a stable `interacted` identity and so
                never converges; and a component whose interaction is real but
                whose outcome never changes (e.g. a login submit retried
                against invalid credentials), which correctly stays
                `interacted` itself but doesn't reduce the page's overall
                debt either. A page still making real progress (each attempt
                reveals something new) never trips this - see
                `_apply_diminishing_returns`.
            deep_context: Whether to read a deeper "what is this site/app for" text
                from the root page once, at the start of Discovery, and surface it on
                every iteration prompt (see `_establish_site_context`) - grounds the
                model in what business/domain it's crawling (e.g. "this sells
                empanadas") before it starts choosing actions, rather than only ever
                seeing route names and short per-page descriptions. Deliberately no
                extra LLM call - see `_establish_site_context`'s docstring for why:
                the raw extracted text is used directly. Falls back to
                `PageState.description` when the active scraper doesn't implement
                `Scraper.extract_context` (e.g. `RestScraper` - a known gap, see
                docs/explicativos/pendientes-futuras-fases.md). Default on; set False
                to skip entirely (e.g. to save the extra page read on a very slow
                site, or when the root page's content isn't representative).
            context_max_chars: Upper bound passed to `Scraper.extract_context()`.
        """
        self.agent = agent
        self.scraper = scraper
        self.graph_store = graph_store or InMemoryGraphStore()
        self.progress_file = progress_file
        self.progress_log_file = progress_log_file
        self.graph_log_file = graph_log_file
        self.components_log_file = components_log_file
        self.components_catalog_file = components_catalog_file
        self.max_iterations = max_iterations
        self.batch_size = batch_size
        self.pending_batch_size = pending_batch_size if pending_batch_size is not None else batch_size
        self.component_batch_size = component_batch_size if component_batch_size is not None else batch_size
        self.allow_subdomains = allow_subdomains
        self.max_stalled_finish_attempts = max_stalled_finish_attempts
        self.docs_client = docs_client or DocsClient()
        self.deep_context = deep_context
        self.context_max_chars = context_max_chars
        # Set once, from the root page, by _establish_site_context - a persistent,
        # whole-run "what is this site/app for" line surfaced on every iteration
        # prompt (see _build_iteration_prompt) and folded into _create_plan's
        # prompt too. "" when deep_context is off or nothing usable was extracted -
        # every consumer already treats an empty context_line as "omit it".
        self.site_context: str = ""
        # Load specialized skills. Note: PROGRESS.md is written mechanically by
        # _update_progress() below - the LLM is never asked to author it, so the
        # "archaeology-progress-tracker" skill is intentionally not loaded/used
        # as a system_instruction (it previously was, and its "update PROGRESS.md
        # with a table" instructions conflicted with the GOTO/CLICK/FINISH format
        # expected during the decision loop, causing the model to emit progress
        # tables instead of actions).
        self.archeologist_skill = self._load_skill("archeologist-skill")
        self.dom_mapper_skill = self._load_skill("dom-mapper-skill")
        self.component_catalog_skill = self._load_skill("component-catalog-skill")

        # Track discovery state. The graph itself (pages/edges) lives in
        # self.graph_store, not here - self.base_domain doubles as the "site"
        # key used to scope every graph_store call.
        self.base_domain: Optional[str] = None
        self.plan_summary: str = ""
        self._last_action_error: Optional[str] = None
        # Label of the action that failed last iteration (e.g. "click 3"),
        # surfaced once into the *next* prompt via _last_error_line() then
        # cleared - without this the model previously had zero feedback about
        # why its last action failed and would often blindly repeat it.
        self._last_failed_action: Optional[str] = None
        # Consume-once, same shape as _last_failed_action/_last_error_line: the
        # text of the last `help` lookup, surfaced into the *next* prompt only
        # (see _last_error_line's sibling, the guidance line in
        # _build_iteration_prompt) then cleared - guidance is meant to be
        # consulted in the moment, not accumulated across the whole run.
        self._pending_help_topic: Optional[str] = None
        self._pending_help_text: Optional[str] = None
        # Every visited page's PageState.description, keyed by cleaned url -
        # accumulated (never overwritten mid-run by _update_progress's
        # per-call overwrite) so the final synthesis step actually has access
        # to what each page is *about*, not just its route/label. See
        # _record_description and _build_descriptions_block: this is folded
        # into progress_file's always-current content, not just the
        # append-only debug log, because _synthesize_tree_report only ever
        # reads progress_file's live snapshot back in.
        self._page_descriptions: dict[str, str] = {}
        # The per-page component ledger itself ({cleaned page url: {component
        # path: {tag, text, interacted, interactions}}}) now lives in
        # `graph_store` (see GraphStore.record_component/record_component_interaction/
        # get_component_ledger), not here - persisted so it survives a page
        # revisit or a new run against the same site, and so the loop can
        # actually consult "was this interacted with" instead of only logging
        # it. `_write_component_ledger` reads it back from the store to write
        # `components_log_file` once the run finishes - the durable "what did I
        # do on this page, and to what" record a route/edge list alone doesn't
        # give (an edge only records navigations that changed page state, not
        # every attempted interaction, and never says what *wasn't* touched).
        # Set by _build_iteration_prompt on every call, read by
        # _reject_premature_finish right after - how many currently-visible
        # components in *this turn's* prompt had never been shown before.
        # Counted on the very first prompt of the run too, deliberately - a
        # real crawl (empanad.app) showed the model responding `finish` on
        # its very first turn, having been shown the root page's components
        # for the first time and clicked nothing at all. The previous version
        # of this guard suppressed the count on turn one on the theory that
        # "everything is trivially new then, not a sign anything changed" -
        # true for the SPA-reveal signal this exists to catch, but that
        # reasoning doesn't apply to "have these components ever actually
        # been looked at," which is exactly as true on turn one as any other
        # turn. See _build_iteration_prompt's comment for why this has to be
        # captured at prompt-build time, not recomputed afterward.
        self._last_new_component_count: int = 0
        self._dna_index_map: dict = {}
        # Paths already offered to the model in some previous iteration's
        # Clickable elements list (see _build_iteration_prompt) - used to keep
        # re-showing the same already-seen elements from crowding out ones
        # that have never been shown yet, once both compete for a batch_size
        # slot. Never reset mid-run: a component only needs to be surfaced once.
        self._shown_component_paths: set = set()
        # Selector last clicked/filled/submitted when doing so did *not*
        # navigate (a toggle-style trigger - opens/closes a menu in place).
        # None whenever the last action was a real navigation or the run just
        # started. See the repeat-target guard in _execute_loop: a dropdown
        # trigger commonly *closes what it just opened* on a second identical
        # click (observed on a real crawl - re-clicking "Academic Offerings"
        # made "Grade"/"Postgraduate"/etc. disappear again), so immediately
        # repeating the exact same target is never useful and is blocked
        # rather than left to the model to avoid on its own.
        self._last_inplace_target_path: Optional[str] = None
        # Rolling window of recent in-place (non-navigating) target paths, for
        # `_warn_if_oscillating` - `_last_inplace_target_path` alone only catches
        # the *exact same* target twice in a row (a toggle re-closing what it
        # opened); it misses a short cycle between two or more distinct targets
        # that never advances (observed on a real crawl: click a combobox
        # trigger, fill a field that turned out to have nothing further to do,
        # click the trigger again, ...). That pattern usually means some
        # interactive element on the page still isn't being discovered (see
        # PlaywrightScraper._discover_components's two-layer selector) - this
        # doesn't fix or override the model's choices (see this method's
        # docstring on why _execute_loop never does that), it just makes that
        # situation loud in the log instead of silently burning the whole
        # iteration budget before anyone notices.
        self._recent_targets: List[str] = []
        # Diminishing-returns tracking for _reject_premature_finish, keyed by
        # cleaned page url: {url: unexplored_count last seen for that page when
        # the finish guard checked it}. A repeated check that finds the count
        # hasn't strictly improved (gone down) increments {url: strike_count}
        # in `_page_debt_strikes`; once a page's strikes reach
        # `max_stalled_finish_attempts`, it moves into `_given_up_pages` and
        # its remaining debt stops blocking `finish` from then on. This is the
        # fix for two real, related failure modes: (1) a component whose
        # underlying CSS path shifts every time a sibling is added/removed
        # (e.g. a quantity stepper's "+"/"-" buttons) never actually
        # accumulates `interacted: True` under a stable identity - each click
        # looks like a "new" never-touched component, so the debt count
        # oscillates (11 -> 13 -> 11 -> 13...) and never converges; (2) a
        # component whose interaction is real but whose outcome doesn't change
        # (e.g. a login submit tried repeatedly against invalid credentials)
        # correctly stays "interacted" itself, but real attempts spent on it
        # don't reduce the *page's* overall debt either. Both cases share the
        # same observable signature - repeated real effort, no shrinking
        # debt - so both are caught by the same page-level, no-progress
        # circuit breaker rather than needing to separately diagnose "why."
        # A page where genuine progress is still happening (each interaction
        # reveals new content, e.g. a filter that surfaces new result
        # components each time a different value is tried) keeps resetting its
        # strikes back to zero and is never given up on early.
        self._page_debt_strikes: dict = {}
        self._page_last_debt: dict = {}
        self._given_up_pages: set = set()

    def _load_skill(self, skill_name: str) -> Optional[str]:
        """Load a specific skill from the .gemini/skills directory."""
        root = pathlib.Path(__file__).resolve().parents[2]
        skill_path = root / ".gemini" / "skills" / skill_name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")
        return None

    def generate_prd(self, url: str) -> str:
        """Execute a deep research loop and synthesize the final tree map."""
        print(f"Phase 1/4: Deep Discovery on {url}")
        state = self.scraper.navigate(url)

        # Initialize discovery tracking
        self.base_domain = self._get_domain(url)
        self._upsert(url, status="Finished", components=len(state.components), context="Root")
        self._record_page_inventory(state)
        self._update_discovered_routes(state.links, source=url)
        self._record_description(url, state.description)
        self._establish_site_context(state)
        self._update_progress(
            "DISCOVERY",
            f"Root page: {url}\nComponents found: {len(state.components)}\n"
            f"Links found: {len(state.links)}",
        )

        print("Phase 2/4: Planning Exhaustive Research Strategy")
        plan = self._create_plan(state)
        self.plan_summary = plan[:300]
        self._update_progress("PLAN CREATED", plan)

        print("Phase 3/4: Executing High-Fidelity Interaction Loop")
        self._execute_loop(state)
        self._write_graph_log()
        self._write_component_ledger()
        self._write_component_catalog()

        print("Phase 4/4: Synthesizing Hierarchical System Mind-Map")
        report = self._synthesize_tree_report()
        if self.progress_log_file:
            append_output(self.progress_log_file, f"## SYNTHESIS\n\n{report}\n\n---\n\n")
        return report

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for filtering."""
        from urllib.parse import urlparse
        return urlparse(url).netloc

    def _clean_url(self, url: str) -> str:
        """Normalize a URL into a graph-node key: drop scheme and trailing slash,
        and drop the fragment unless it looks like a client-side route.

        A route discovered via an http:// link almost always redirects to
        https:// (or vice versa) - without stripping the scheme, the two
        variants were treated as distinct graph nodes, so visiting one via its
        canonical form never marked the other "Finished". The crawler would
        then ping-pong between the http:// and https:// variants of the exact
        same page indefinitely, since both kept showing up as "Pending".

        Fragments are more ambiguous: `#section` is almost always an in-page
        anchor (same content, just scrolled), but `#/products/123` is commonly
        a hash-based SPA router's actual route (genuinely different content,
        same static HTML shell) - unconditionally stripping every fragment, as
        this used to, collapsed every such route into one node, so a crawl of
        a hash-routed SPA would only ever discover its single root "page" and
        never surface any of its distinct views as Pending routes. The
        heuristic here is deliberately simple (a fragment containing `/` is
        treated as a route, kept distinct; anything else is treated as an
        anchor, dropped) - a bare-segment router with no leading `/` (e.g.
        `#products`) won't be recognized as a route by this and is a known,
        documented v1 gap rather than something solved speculatively here.
        """
        base, _, fragment = url.partition("#")
        base = base.rstrip("/")
        for prefix in ("https://", "http://"):
            if base.startswith(prefix):
                base = base[len(prefix):]
                break
        if "/" in fragment:
            return f"{base}#{fragment.rstrip('/')}"
        return base

    def _upsert(self, url: str, status: str = "Pending", components: int = 0, context: str = "", label: str = "") -> None:
        """Normalize a URL into its graph-node key and upsert it into the graph store."""
        self.graph_store.upsert_page(
            self.base_domain, self._clean_url(url), status=status, components=components,
            context=context, label=label,
        )

    def _domain_in_scope(self, href_domain: str) -> bool:
        """Whether a link's domain counts as "same site" for route discovery.

        Exact match always counts. When `allow_subdomains` is on, a domain
        sharing the same last-two-label root also counts (e.g.
        blog.example.com and example.com both match example.com's root) - a
        naive heuristic (not a full public-suffix-list lookup: `co.uk`-style
        multi-part public suffixes would over-match), consistent with the
        project's no-heavy-deps approach elsewhere (e.g. no NLP in
        `_extract_description`). Off by default, matching the exact-netloc
        behavior this replaces.
        """
        if href_domain == self.base_domain:
            return True
        if not self.allow_subdomains or not href_domain or not self.base_domain:
            return False
        href_root = ".".join(href_domain.split(".")[-2:])
        base_root = ".".join(self.base_domain.split(".")[-2:])
        return href_root == base_root

    def _update_discovered_routes(self, links: list, source: str) -> None:
        """Add new in-scope links to the discovery list.

        Non-http(s) schemes (mailto:, tel:, javascript:, ...) are captured on
        the link itself (see PlaywrightScraper._extract_links) but never
        queued as pending routes here - there's nothing to navigate to, so
        adding them would just be a permanently-unreachable "Pending" entry.
        Explicitly counted and logged (`_update_progress`), not silently
        dropped, so a page with many such links doesn't look identical to one
        with none.
        """
        skipped_schemes = 0
        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                skipped_schemes += 1
                continue
            if self._domain_in_scope(self._get_domain(href)):
                label = link.get("text", "")
                self._upsert(href, context=source, label=label)
                # Recorded per (source, href) pair, not just onto the destination
                # page - a page can be linked to from many different source pages
                # with different anchor text, and a later GOTO's component
                # description must only claim a link that actually exists on the
                # page it's navigating from (see _describe_component).
                self.graph_store.record_link(
                    self.base_domain, self._clean_url(source), self._clean_url(href), label
                )
        if skipped_schemes:
            self._update_progress(
                "DISCOVERY",
                f"{skipped_schemes} non-navigable link(s) (mailto/tel/javascript/etc.) found on "
                f"{source}, not queued as pending routes.",
            )

    def _create_plan(self, state: PageState) -> str:
        """Create a step-by-step research plan for deep excavation."""
        pending = self.graph_store.get_pending(self.base_domain)
        shown = pending[: self.pending_batch_size]
        prompt = (
            f"{self._site_context_line()}"
            f"High-Fidelity Observation of {state.url}\n"
            f"Title: {state.title}\n"
            f"Detected Components: {len(state.components)}\n"
            f"Initial Discovered Routes ({len(shown)} of {len(pending)} shown): "
            f"{json.dumps(shown)}\n"
            "Create a plan to exhaustively map this system's tree structure. "
            "You MUST explore all discovered routes to complete the map, one at a time."
        )
        return self.agent.generate(prompt, system_instruction=self.archeologist_skill)

    def _update_progress(self, stage: str, details: str) -> None:
        """Overwrite the live status snapshot, and append to the debug trail."""
        finished, total = self.graph_store.count_visited(self.base_domain)
        perc = (finished / total * 100) if total > 0 else 0

        header = (
            f"# Archaeology Progress: {self.base_domain}\n\n"
            f"## Status: {finished}/{total} ({perc:.1f}%)\n\n"
        )

        table = self._build_progress_table()
        descriptions = self._build_descriptions_block()
        content = f"{header}{table}\n\n{descriptions}## Log: {stage}\n\n{details}\n\n---\n"
        write_output(self.progress_file, content)

        if self.progress_log_file:
            append_output(
                self.progress_log_file,
                f"## {stage} ({finished}/{total} visited)\n\n{details}\n\n---\n\n",
            )

    def _build_progress_table(self) -> str:
        """Build a compact markdown table for route discovery progress."""
        table = "## Route Map\n\n| Route | Status | Label |\n|-------|--------|-------|\n"

        # List all routes to ensure the audit trail is complete
        for row in self.graph_store.get_progress_table_rows(self.base_domain):
            table += f"| {row['url']} | {row['status']} | {row['label']} |\n"
        return table

    def _record_description(self, url: str, description: str) -> None:
        """Remember a visited page's PageState.description (if any), keyed by
        its cleaned url - see `_page_descriptions` in __init__ for why this
        lives in an accumulator rather than only `_update_progress`'s
        per-call `details`, which gets overwritten before synthesis ever
        reads it back."""
        if description:
            self._page_descriptions[self._clean_url(url)] = description

    def _build_descriptions_block(self) -> str:
        """Render every visited page's description as its own section in the
        always-current `progress_file` content - this, not the append-only
        debug log, is what `_synthesize_tree_report` reads back in, so this
        is the actual mechanism by which "what is this app/page about" text
        reaches the final PRD rather than being logged and then lost."""
        if not self._page_descriptions:
            return ""
        lines = ["## Page Descriptions\n"]
        for url, description in self._page_descriptions.items():
            lines.append(f"- **{url}**: {description}")
        return "\n".join(lines) + "\n\n"

    def _establish_site_context(self, state: PageState) -> None:
        """Set `self.site_context` once, from the root page - a whole-run "what is
        this site/app for" grounding line, distinct from `state.description`'s
        per-page (and much terser) context.

        Deliberately no LLM call: an earlier design summarized the extracted text
        into a short model-written blurb via one extra `agent.generate()` at the
        start of the run, but every call site that drives the decision loop reuses
        the same `ScriptedAgent`-style script-of-responses pattern used throughout
        this project's tests (`agent.act()`/`agent.generate()` both draw from one
        shared, ordered script) - inserting an unconditional extra `generate()` call
        here would silently shift every existing script by one entry. Using the
        scraper's own extracted text directly avoids a model call entirely (cheaper,
        faster, and per wiki/local-and-small-model-constraints.md's preference for
        deterministic signals over model judgment wherever the underlying facts are
        already mechanically available - the same reasoning `component_classifier.py`
        follows), at the cost of the text being page-content-as-is rather than a
        polished summary.

        Falls back to `state.description` (already-available, no extra scraper call)
        when `self.deep_context` is off, the active `Scraper` doesn't implement
        `extract_context` (e.g. `RestScraper` - Module 3's `/dynamic/*` has no
        matching route yet, a known gap - see
        docs/explicativos/pendientes-futuras-fases.md), or the deeper extraction
        raised for any other reason - a missing/failed context grounding should
        never abort a run that would otherwise work fine without it.
        """
        if not self.deep_context:
            return
        try:
            context = self.scraper.extract_context(max_chars=self.context_max_chars)
        except NotImplementedError:
            context = state.description
        except Exception as exc:  # noqa: BLE001 - degrade to no site context, don't abort the run
            print(f"Warning: extract_context failed, falling back to page description: {exc}")
            context = state.description
        self.site_context = (context or "").strip()
        if self.site_context:
            self._update_progress("CONTEXT", f"Site context established:\n{self.site_context}")

    def _site_context_line(self) -> str:
        """Persistent prompt line surfacing `self.site_context` - shown every
        iteration (unlike `_last_error_line`/`_pending_guidance_line`, which
        consume themselves once shown), since "what is this site for" stays true
        for the whole run, not just the next turn."""
        return f"Site purpose (established from the landing page): {self.site_context}\n" if self.site_context else ""

    def _execute_loop(self, state: PageState) -> None:
        """The core iteration loop for deep component discovery.

        A malformed or failed action skips that iteration rather than aborting
        the whole run - a single bad response from a flaky/small model, or one
        failed click, shouldn't cut a run short after visiting only a handful
        of the discovered routes. The agent decides every iteration; the engine
        doesn't second-guess or override its choices, only records outcomes -
        see PlaywrightScraper.click() for why click failures now surface here
        as a genuine failure instead of a silent, indistinguishable no-op.

        `i` (real, budgeted iterations) and `passes` (total loop turns) are
        tracked separately so a `help` lookup - which doesn't change page state
        and shouldn't cost the same as a real research step - doesn't consume
        `max_iterations`. `passes` is still hard-capped (at a small multiple of
        `max_iterations`) as a safety valve against a model stuck asking for
        help forever without ever acting.
        """
        current_state = state
        i = 0
        passes = 0
        max_passes = self.max_iterations * 3
        while i < self.max_iterations and passes < max_passes:
            passes += 1
            from_url = current_state.url

            prompt = self._build_iteration_prompt(current_state)
            action = self.agent.act(prompt, system_instruction=self.archeologist_skill)

            if action.kind == "help":
                topic = action.value or ""
                print(f"Help requested: {topic}")
                self._pending_help_topic = topic
                self._pending_help_text = self.docs_client.get(topic)
                self._update_progress("HELP", f"Asked for '{topic}': {self._pending_help_text}")
                continue  # does not consume the `i` budget - see docstring

            i += 1
            print(f"Research Iteration {i}...")
            print(f"Action: {action.raw}")

            if action.kind == "finish":
                if self._reject_premature_finish(i, current_state.url):
                    continue
                self._update_progress(f"ITERATION {i}", "Agent concluded research.")
                break

            if action.kind == "unknown":
                print("Warning: response was not a valid action, skipping.")
                self._update_progress(
                    f"ITERATION {i}",
                    f"Agent response was not a valid action (ignored):\n{action.raw[:500]}",
                )
                continue

            # Graph-traversal guard: refuse to re-navigate to an already-visited
            # node. This is a cheap, explicit check (no page load spent) on top
            # of the "Pending" list already excluding visited routes - it's the
            # safety net for cases like scheme (http/https) duplicates or the
            # model simply not following instructions. A page in
            # `_given_up_pages` (see `_apply_diminishing_returns`) counts as
            # fully covered here too, even though real component debt is still
            # technically recorded for it - repeated attempts already proved
            # that debt isn't shrinking, so a revisit would just resume the
            # same non-improving cycle the give-up decision was meant to stop.
            if (
                action.kind == "navigate"
                and action.url
                and self._already_visited(action.url)
                and (
                    self._clean_url(action.url) in self._given_up_pages
                    or not self.graph_store.page_has_unexplored_components(
                        self.base_domain, self._clean_url(action.url)
                    )
                )
            ):
                node = self._clean_url(action.url)
                print(f"Already visited {node}, skipping re-navigation.")
                self._update_progress(
                    f"ITERATION {i}",
                    f"navigate {action.url} skipped: {node} is already visited in the graph "
                    "and has no unexplored components left.",
                )
                continue

            target_path = self._resolve_target_path(action)
            if target_path and target_path == self._last_inplace_target_path:
                self._skip_repeated_target(i, action)
                continue

            next_state = self._execute_action(action)
            if next_state is None:
                reason = f" Reason: {self._last_action_error}" if self._last_action_error else ""
                print(f"Warning: action did not produce a new page state, skipping.{reason}")
                self._last_failed_action = self._action_label(action)
                self._update_progress(
                    f"ITERATION {i}",
                    f"Action failed to produce a new page state (ignored):\n{action.raw}\n{reason}",
                )
                continue

            in_place = next_state.url == from_url
            self._last_inplace_target_path = target_path if in_place else None
            if in_place and target_path:
                self._track_oscillation(i, target_path)
            else:
                self._recent_targets = []
            self._handle_iteration_result(i, action, from_url, next_state, current_state.components)
            current_state = next_state

    def _track_oscillation(self, iter_num: int, target_path: str) -> None:
        """Warn (never override - see `_execute_loop`'s docstring) when the last
        few in-place actions form a stuck cycle between the same 2-3 targets
        with no forward progress - the exact-repeat guard (`_last_inplace_target_path`)
        only catches the same target twice *in a row*, not a short back-and-forth
        cycle between distinct targets that never advances. In practice this has
        meant a real interactive element on the page still isn't being discovered
        (see PlaywrightScraper._discover_components) - surfacing it loudly here
        makes that fast to notice instead of silently spending the whole
        `max_iterations` budget going nowhere.
        """
        window = 6
        threshold = 3
        self._recent_targets.append(target_path)
        self._recent_targets = self._recent_targets[-window:]
        if self._recent_targets.count(target_path) < threshold:
            return
        message = (
            f"Possible stuck loop: target {target_path!r} repeated {threshold}+ times in the "
            f"last {window} in-place actions without reaching a new page. This usually means an "
            "interactive element on the page isn't being discovered (e.g. a custom widget with no "
            "semantic tag or ARIA role and no cursor:pointer style) - inspect this page's DOM "
            "directly (PlaywrightScraper against the stuck URL) rather than assuming it's a model "
            "or tool-calling issue."
        )
        print(f"WARNING: {message}")
        self._update_progress(f"ITERATION {iter_num}", message)

    def _resolve_target_path(self, action: AgentAction) -> Optional[str]:
        """The real selector a click/fill/submit action's `ref` points at, if any.

        Returns None for navigate/finish/unknown actions or an unresolvable
        ref - this is a lookup for the repeat-target guard, not execution
        (see `_resolve_ref_selector` for the raising version used to actually
        act), so an unresolvable ref should just fail to match, not error.
        """
        if action.kind in ("click", "fill", "submit") and action.ref is not None:
            comp = self._dna_index_map.get(action.ref)
            return comp["path"] if comp else None
        return None

    def _reject_premature_finish(self, iter_num: int, current_url: str) -> bool:
        """Block `finish` when either of two independent conditions holds; return
        True if blocked (caller should `continue`), False if finish should
        actually proceed. Both checks only ever refuse `finish` - neither
        substitutes a different action - staying inside the same narrow
        "decline, don't override" exception `_execute_loop`'s docstring
        documents for every other guard.

        A single check, sourced from `graph_store`'s persisted component
        states rather than any turn-local/in-process signal: does *any* page
        this run has recorded (the current page included) still have a
        component that's been shown but never actually interacted with
        (click/fill/submit)? `semantic_only=False` - unlike the store's
        default - deliberately includes the `layer="pointer"` catch-all: a
        real crawl (empanad.app) showed the model filling one field then
        finishing immediately, ignoring two other real, clickable components
        on the same page that only the cursor:pointer fallback layer found
        (common for component-library widgets - Radix/shadcn/MUI/custom
        design systems - built from `<div>`s with no semantic tag or ARIA
        role at all). Excluding that layer from this check meant a whole
        class of real, library-built interactive elements could never block
        completion, no matter how many were left untouched.

        This deliberately does NOT stop at "has this been shown" (the
        original, narrower version of this guard, before a real run exposed
        the gap above) - "shown" only proves the model glanced at a list, not
        that it did anything. Requiring `interacted` is the one deliberate
        exception to "the engine never overrides the model's choices" (see
        `_execute_loop`'s docstring): `finish` is terminal, unlike a bad
        click/fill there's no next turn to recover in, and a prompt-only nudge
        already proved insufficient (the empanad.app 3->11-components case
        this guard was originally built for, and the pointer-layer case
        above) - both times an *informational* line alone was read as
        "nothing left to do."

        `current_url` is not excluded, unlike an earlier version of this
        check: a component shown once but never touched is exactly as
        unfinished on the same turn it appeared as it is ten turns later on
        the same page - "already shown" was never actually evidence anything
        was looked at.

        Termination stays safe even without the next paragraph's mechanism:
        `max_iterations` is an unconditional outer cap this check cannot
        affect - a site whose debt never clears simply exhausts its budget
        and ends normally, as with any other unresolved guard.

        Before blocking, `_apply_diminishing_returns` filters out any page
        whose debt has stopped shrinking across repeated checks (see its
        docstring and `max_stalled_finish_attempts`) - real crawls showed
        `max_iterations` alone wasn't a *good* backstop, just a safe one: a
        component whose CSS path shifts on every DOM sibling change (a
        quantity stepper) or a login submit retried against invalid
        credentials could each burn most of a run's budget on a single page
        that was never going to converge, leaving little left for the rest of
        the site. This still only ever *removes* a page from the blocking set
        - it never substitutes an action - so it stays inside the same
        "decline, don't override" posture as everything else here.
        """
        debt_pages = self.graph_store.get_pages_with_unexplored_components(
            self.base_domain, limit=None, semantic_only=False
        )
        debt_pages = self._apply_diminishing_returns(debt_pages)
        if not debt_pages:
            return False
        debt_pages = debt_pages[:6]

        current_key = self._clean_url(current_url)
        names = ", ".join(f"{row['url']} ({row['unexplored_count']})" for row in debt_pages)
        on_current = next((row for row in debt_pages if row["url"] == current_key), None)
        if on_current:
            detail = (
                f"{on_current['unexplored_count']} element(s) on the current page remain unexplored "
                "(shown but never interacted with) - investigate them before finishing. An empty "
                "Pending routes list does not mean nothing is left: this includes elements built by a "
                "component library (no native tag or ARIA role), not just standard buttons/links/inputs."
            )
        else:
            detail = (
                f"pages you've already left have components that remain unexplored: {names}. "
                "Navigate back to one of them and continue before finishing."
            )
        print(f"finish rejected: unexplored components remain: {names}")
        self._last_failed_action = "finish"
        self._last_action_error = detail
        self._update_progress(f"ITERATION {iter_num}", f"finish rejected: {detail}")
        return True

    def _apply_diminishing_returns(self, debt_pages: list) -> list:
        """Filter `debt_pages` (from `graph_store.get_pages_with_unexplored_components`),
        removing any page whose debt has stopped improving across repeated checks -
        see `max_stalled_finish_attempts`'s docstring in `__init__` for the two real
        failure modes this exists to break: a component whose CSS path shifts every
        time a DOM sibling is added/removed (never accumulates a stable `interacted`
        identity, so debt oscillates instead of shrinking), and a component whose
        interaction is real but whose outcome never changes (debt just plateaus).

        Called with the *full* (unlimited) debt list, not a capped slice - a page
        ranked outside whatever display limit the caller uses downstream must still
        have its strikes tracked every time, or it could stall unnoticed forever
        without ever being given up on.

        Every call here is a real "was this page's debt checked and found no better
        than last time" event, since it only runs from `_reject_premature_finish`,
        itself only invoked when the model actually attempts `finish` - so strikes
        accumulate at the same pace real finish attempts happen, not on some
        independent timer.
        """
        result = []
        for row in debt_pages:
            url, count = row["url"], row["unexplored_count"]
            if url in self._given_up_pages:
                continue
            last = self._page_last_debt.get(url)
            if last is not None and count >= last:
                strikes = self._page_debt_strikes.get(url, 0) + 1
                self._page_debt_strikes[url] = strikes
                if strikes >= self.max_stalled_finish_attempts:
                    self._given_up_pages.add(url)
                    print(
                        f"Giving up on {url}: unexplored count stayed at/above {count} for "
                        f"{strikes} consecutive checks - likely a component whose identity "
                        "shifts on every interaction (e.g. a stepper) or whose outcome never "
                        "changes (e.g. a login retry). Its remaining debt no longer blocks finish."
                    )
                    self._update_progress(
                        "DIMINISHING RETURNS",
                        f"Gave up on {url}'s remaining {count} unexplored component(s) after "
                        f"{strikes} checks with no improvement.",
                    )
                    continue
            else:
                self._page_debt_strikes[url] = 0
            self._page_last_debt[url] = count
            result.append(row)
        return result

    def _skip_repeated_target(self, iter_num: int, action: AgentAction) -> None:
        """Handle a click/fill/submit that repeats the previous iteration's
        in-place (non-navigating) target - see `_last_inplace_target_path`'s
        docstring in __init__ for why this is blocked rather than executed:
        a dropdown trigger can *close* what it just opened on a second
        identical click, oscillating forever with no forward progress.
        """
        print("Repeating last iteration's in-place target, skipping.")
        self._last_failed_action = self._action_label(action)
        self._last_action_error = (
            "this exact element was just interacted with and led nowhere new - "
            "pick a different element from the list, or finish if nothing new remains"
        )
        self._update_progress(
            f"ITERATION {iter_num}",
            f"{action.kind} {action.ref} skipped: repeats the previous iteration's "
            "target without producing a new page.",
        )

    def _action_label(self, action: AgentAction) -> str:
        """Short human label for an action, used in the next prompt's failure note."""
        if action.kind == "navigate":
            return f"navigate {action.url}"
        if action.ref is not None:
            return f"{action.kind} {action.ref}"
        return action.kind

    def _already_visited(self, url: str) -> bool:
        """Whether a URL is already a Finished node in the navigation graph."""
        return self.graph_store.is_visited(self.base_domain, self._clean_url(url))

    def _build_iteration_prompt(self, state: PageState) -> str:
        """Build a bounded prompt for a single discovery iteration.

        Pending routes and page DNA are capped at `batch_size` each, so a single
        iteration's prompt (and inference time) stays roughly constant no matter
        how large the site is - the tradeoff is needing more iterations to work
        through everything. DNA elements are shown as a short numbered list (tag
        + text, plus type/placeholder/disabled when present - never the full CSS
        path or attributes.class) and click/fill/submit refer to them by number -
        the full path/class list used to be dumped verbatim per element, which on
        CSS-framework-heavy sites can be hundreds of characters each and was
        likely the single biggest driver of prompt size (and inference time).

        Which `batch_size` components get shown is *not* just "the first N in
        DOM order" - see `_select_dna_components`: on a real nav-heavy page, a
        dropdown/mega-menu's items can sit hundreds of positions deep in raw
        DOM order even though they're present (just CSS-hidden) from page load,
        so a pure DOM-order slice can permanently bury them behind the cap no
        matter how many times the model clicks the trigger that reveals them.
        """
        cleaned_url = self._clean_url(state.url)
        pending = self.graph_store.get_pending(self.base_domain)
        shown_pending = pending[: self.pending_batch_size]
        # One query for every component ever recorded on this page, consulted
        # instead of recomputed each turn from the live DOM alone - this is what
        # lets a component interacted with in a *previous run* (graph_store: neo4j,
        # fresh: false) be correctly recognized as such on turn one of a new run,
        # something an in-process, never-persisted set could never know.
        states = self.graph_store.get_component_states(self.base_domain, cleaned_url)
        shown_components = self._select_dna_components(state.components, states)

        self._dna_index_map = {}
        dna_lines = []
        new_count = 0
        for idx, comp in enumerate(shown_components, 1):
            text = (comp.get("text") or "").strip()[:60]
            self._dna_index_map[idx] = {
                "path": comp.get("path", ""),
                "tag": comp.get("tag", ""),
                "text": text,
                # input_type/placeholder/label/name aren't shown to the model beyond
                # what _describe_dna_element already renders, but _execute_action's
                # fallback needs them to synthesize a value when a fill's `value`
                # comes back empty - see _generate_field_value.
                "input_type": comp.get("input_type", ""),
                "placeholder": comp.get("placeholder", ""),
                "label": comp.get("label", ""),
                "name": comp.get("name", ""),
                # Empty string for the overwhelming common case (main page) - only
                # set when the scraper tagged this component as discovered inside
                # an iframe (see PlaywrightScraper._discover_components). Read by
                # _execute_action to target the right document.
                "frame_url": comp.get("frame_url", ""),
            }
            path = comp.get("path", "")
            if path:
                # Refreshes text/visibility for the subset actually shown this
                # turn - `_record_page_inventory` (called once per new page,
                # from `_handle_iteration_result`/`generate_prd`) already
                # recorded every component including position; `rect` is
                # passed through here too so this refresh doesn't null out
                # that position data on the next call (record_component's
                # ON MATCH SET always writes x/y/width/height verbatim).
                rect = comp.get("rect") or {}
                self.graph_store.record_component(
                    self.base_domain, cleaned_url, path,
                    tag=comp.get("tag", ""), text=text, role=comp.get("role", ""),
                    input_type=comp.get("input_type", ""), visible=comp.get("visible", True),
                    layer=comp.get("discovery_layer", "semantic"),
                    x=rect.get("x"), y=rect.get("y"), width=rect.get("width"), height=rect.get("height"),
                )
            interacted = states.get(path, {}).get("interacted", False)
            dna_lines.append(f"[{idx}] {self._describe_dna_element(comp, text, interacted=interacted)}")
            if path:
                # Counted *before* adding to _shown_component_paths below, not after -
                # this is "how many of the elements I'm about to show right now have
                # never been shown before", which is exactly what _reject_premature_finish
                # needs to know once the model responds to *this* prompt. Checking
                # membership after the update below would find everything already
                # "shown" (by this same call) and always report zero new - the bug that
                # let a real crawl's premature `finish` through the first version of
                # this guard.
                if comp.get("visible", True) and path not in self._shown_component_paths:
                    new_count += 1
                self._shown_component_paths.add(path)
        dna_block = "\n".join(dna_lines) if dna_lines else "(none)"
        # `_last_new_component_count` is what _reject_premature_finish checks once the
        # model responds to *this* prompt - see its docstring, and the comment above on
        # why the count has to be captured now rather than recomputed later. Not
        # suppressed on the very first prompt of the run - see the comment on
        # `_last_new_component_count` in __init__ for why turn one isn't exempt.
        self._last_new_component_count = new_count
        change_line = (
            f"Note: {new_count} of the elements below are new - not seen in any previous turn. "
            "Investigate them before calling finish, even if Pending routes is empty (a "
            "single-page app can reveal new content in place, without changing its URL).\n"
            if self._last_new_component_count
            else ""
        )

        plan_line = f"Plan: {self.plan_summary}\n" if self.plan_summary else ""
        site_context_line = self._site_context_line()
        loop_line = self._loop_signal_line(state.url)
        error_line = self._last_error_line()
        guidance_line = self._pending_guidance_line()
        context_line = f"Page context: {state.description}\n" if state.description else ""
        structure_line = self._page_structure_line(shown_components)
        debt_line = self._component_debt_line(cleaned_url)

        return (
            f"{site_context_line}"
            f"{plan_line}"
            f"{error_line}"
            f"{guidance_line}"
            f"You are currently at: {state.url} (already visited - do NOT navigate here again)\n"
            f"{context_line}"
            f"{structure_line}"
            f"{change_line}"
            f"{debt_line}"
            f"{loop_line}"
            f"Pending routes you may navigate to ({len(shown_pending)} of {len(pending)} shown): "
            f"{json.dumps(shown_pending)}\n"
            f"Clickable elements on this page, referenced by number "
            f"({len(shown_components)} of {len(state.components)} shown):\n{dna_block}\n\n"
            "Choose one action: navigate to a Pending route, click/fill/submit a numbered "
            "element, or finish. If unsure how, use help(topic) first."
        )

    def _record_page_inventory(self, state: PageState) -> None:
        """Persist every component discovered on `state` into `graph_store`,
        position included - not just the `component_batch_size`-capped subset
        `_build_iteration_prompt` shows the model that turn.

        This is the deterministic "special iteration" run automatically the
        moment a new page loads (called from `generate_prd` for the root page
        and `_handle_iteration_result` for every page reached afterward) - no
        model call, no iteration budget spent, always accurate the instant a
        page is seen, per wiki/prompt-engineering-for-llm-agents.md Principle
        6 (deterministic signals, not left for the model to request). Without
        this, a component that never happens to win a `component_batch_size`
        slot (e.g. it sits behind 300 higher-priority components) would never
        be persisted at all, and so could never appear as "unexplored debt" -
        it would just silently never exist as far as the checklist is
        concerned.

        Also classifies each component's type (see `component_classifier.
        classify_component_type`) and, from a single snapshot alone (no
        before/after diff needed), detects quantity steppers and named
        radio/checkbox groups - see `_record_single_snapshot_groupings`. A
        revealed dropdown/combobox's options need an actual before/after
        diff around a click instead, so that case is handled separately in
        `_handle_iteration_result`.
        """
        cleaned_url = self._clean_url(state.url)
        for comp in state.components:
            path = comp.get("path", "")
            if not path:
                continue
            rect = comp.get("rect") or {}
            self.graph_store.record_component(
                self.base_domain, cleaned_url, path,
                tag=comp.get("tag", ""), text=(comp.get("text") or "").strip()[:60],
                role=comp.get("role", ""), input_type=comp.get("input_type", ""),
                visible=comp.get("visible", True), layer=comp.get("discovery_layer", "semantic"),
                x=rect.get("x"), y=rect.get("y"), width=rect.get("width"), height=rect.get("height"),
                component_type=classify_component_type(comp),
            )
        self._record_single_snapshot_groupings(cleaned_url, state.components)

    def _record_single_snapshot_groupings(self, cleaned_url: str, components: list) -> None:
        """Detect and persist stepper/choice-group structure that's knowable
        from one page snapshot alone (unlike a revealed dropdown's options,
        which need a before/after diff - see `_handle_iteration_result`).

        Each detected group's members get an `options` JSON blob describing
        the group they belong to - e.g. a stepper's decrement button records
        `{"kind": "stepper_decrement", "paired_with": {...}, "current_value":
        "3"}}`, its increment button the mirror, and its value element
        `"kind": "stepper_value"`. A radio/checkbox group's members each get
        `{"kind": "choice_group_member", "group_name": "...", "choices": [...]}}`
        naming every sibling and which one (if any) is currently checked.
        """
        for stepper in group_steppers(components):
            paired_with = {
                "decrement": stepper["decrement_path"],
                "increment": stepper["increment_path"],
                "value": stepper["value_path"],
            }
            for role, path in (
                ("stepper_decrement", stepper["decrement_path"]),
                ("stepper_increment", stepper["increment_path"]),
                ("stepper_value", stepper["value_path"]),
            ):
                if not path:
                    continue
                self.graph_store.record_component_options(
                    self.base_domain, cleaned_url, path,
                    json.dumps({
                        "kind": role, "paired_with": paired_with,
                        "current_value": stepper["current_value"],
                    }),
                )

        for group_name, members in group_choice_sets(components).items():
            choices = [
                {"text": (m.get("text") or "").strip(), "selected": bool(m.get("selected"))}
                for m in members
            ]
            for member in members:
                path = member.get("path", "")
                if not path:
                    continue
                self.graph_store.record_component_options(
                    self.base_domain, cleaned_url, path,
                    json.dumps({"kind": "choice_group_member", "group_name": group_name, "choices": choices}),
                )

    def _record_component_interaction(self, url: str, path: str, action: AgentAction, resulting_url: str) -> None:
        """Record one interaction against a component's persisted graph_store entry.

        Called from `_handle_iteration_result` for a click/fill/submit whose ref
        resolved to `path` - `navigate`/`finish`/`help` never target a specific
        component, so they never call this. `graph_store.record_component_interaction`
        auto-creates the Component node if `record_component` hasn't run for
        `path` yet (shouldn't happen in practice - a ref can't be acted on
        without having been shown first - but this stays correct either way
        rather than assuming that ordering).
        """
        self.graph_store.record_component_interaction(
            self.base_domain, self._clean_url(url), path,
            action=action.kind, value=action.value, resulting_url=self._clean_url(resulting_url),
        )

    def _write_component_ledger(self) -> None:
        """Write the full per-page component ledger as JSON, once the run finishes.

        Sourced from `graph_store.get_component_ledger` - the durable "what did
        I do on this page, and to what" record neither the navigation graph
        (only records edges that changed page state, not every attempted
        interaction) nor the progress log (overwritten/not structured for this)
        gives. Reading this back from the store (rather than a parallel
        in-process copy) means the file reflects real persisted state, the same
        state the loop itself consults turn to turn.
        """
        if self.components_log_file:
            ledger = self.graph_store.get_component_ledger(self.base_domain)
            write_output(self.components_log_file, json.dumps(ledger, indent=2))

    def _build_page_catalog_facts(self, page_components: dict) -> List[dict]:
        """Turn one page's ledger entries into a list of catalog-ready fact
        dicts, collapsing a stepper's 2-3 members or a choice-group's N
        members into one entry each - the model is asked to describe "the
        control," not each of its parts separately (see component-catalog-
        skill's rules). Iterates paths in sorted order so output is stable
        run to run for the same underlying data.
        """
        facts: List[dict] = []
        covered_stepper_keys = set()
        covered_group_names = set()
        for path in sorted(page_components.keys()):
            record = page_components[path]
            try:
                options = json.loads(record.get("options") or "{}")
            except json.JSONDecodeError:
                options = {}
            kind = options.get("kind")

            if kind in ("stepper_decrement", "stepper_increment", "stepper_value"):
                paired = options.get("paired_with") or {}
                key = tuple(sorted(v for v in paired.values() if v))
                if not key or key in covered_stepper_keys:
                    continue
                covered_stepper_keys.add(key)
                facts.append(
                    {
                        "type": "stepper control (increment/decrement)",
                        "text": record.get("text") or "quantity control",
                        "current_value": options.get("current_value"),
                        "interacted": record.get("interacted", False),
                    }
                )
                continue

            if kind == "choice_group_member":
                group_name = options.get("group_name") or path
                if group_name in covered_group_names:
                    continue
                covered_group_names.add(group_name)
                facts.append(
                    {
                        "type": "radio/checkbox group",
                        "text": f"group '{group_name}'",
                        "choices": options.get("choices", []),
                        "interacted": record.get("interacted", False),
                    }
                )
                continue

            if kind == "combobox_trigger":
                facts.append(
                    {
                        "type": record.get("component_type") or "combobox trigger",
                        "text": record.get("text") or "",
                        "choices": options.get("choices", []),
                        "interacted": record.get("interacted", False),
                    }
                )
                continue

            if kind == "revealed_option_member":
                # Already represented in full inside its trigger's own
                # "combobox_trigger" fact (`choices`, above) - a separate fact per
                # option here would just repeat every option's text a second time,
                # which is exactly the per-variant duplication this component_type
                # is meant to avoid (see GraphStore.record_component_options'
                # `excluded_from_debt` docstring).
                continue

            # An empty `text` here has already been through the scraper's
            # broadened label fallback chain (innerText -> aria-label/
            # aria-labelledby/title/img-alt/svg-title -> textContent - see
            # PlaywrightScraper._discover_components) and still came up
            # empty. That's now a real fact worth stating plainly - "no
            # accessible label found" - rather than passing '' through to the
            # narration prompt, where it used to read identically to a
            # labelling bug ("Unnamed Element"/"Empty Element") instead of as
            # "this component genuinely has no discoverable label." No CSS
            # selector/path here - the narration skill is explicitly told
            # never to surface implementation details, only what a component
            # is/does.
            text = record.get("text") or "(no accessible label found on this element)"
            facts.append(
                {
                    "type": record.get("component_type") or "element",
                    "text": text,
                    "interacted": record.get("interacted", False),
                }
            )
        return facts

    @staticmethod
    def _render_catalog_fact_line(index: int, fact: dict) -> str:
        """One deterministic-facts line fed into the narration prompt - plain,
        parseable-by-eye key=value pairs, not prose, so the model has exactly
        the verified facts and nothing it has to infer or guess at."""
        parts = [f"type={fact['type']!r}", f"text={fact.get('text', '')!r}", f"interacted={fact.get('interacted')}"]
        if "current_value" in fact:
            parts.append(f"current_value={fact['current_value']!r}")
        if "choices" in fact:
            parts.append(f"choices={fact['choices']!r}")
        return f"{index}. " + " ".join(parts)

    def _write_component_catalog(self) -> None:
        """Write a human-readable, per-component documentation file, once the
        run finishes - not part of `max_iterations`' budget, since it's built
        entirely from already-persisted `graph_store` data after the crawl is
        done, not something that needs the live browser session.

        Each page gets exactly one `agent.generate()` call (batched across all
        of that page's components, not one call per component) - the same
        small-model-conscious batching discipline the rest of this project
        uses (see wiki/local-and-small-model-constraints.md). The deterministic
        facts themselves (type, options, interacted state - see
        `_build_page_catalog_facts`/`component_classifier.py`) are always
        correct regardless of what the model does with them; narration failure
        on one page degrades to including the raw facts for that page instead
        of aborting the whole catalog - this file is a documentation
        enrichment, not something the crawl's correctness depends on, unlike
        the core action loop (see LocalAgent's truncation handling, which
        deliberately does the opposite - fails loudly - for exactly that
        reason: there, a silent failure wastes the whole run's iteration
        budget with nothing to show for it; here, a silent narration failure
        on one page still leaves every other page's entry, plus this page's
        own raw facts, intact).
        """
        if not self.components_catalog_file:
            return
        ledger = self.graph_store.get_component_ledger(self.base_domain)
        sections = []
        for page_url in sorted(ledger.keys()):
            facts = self._build_page_catalog_facts(ledger[page_url])
            if not facts:
                continue
            facts_block = "\n".join(self._render_catalog_fact_line(i, f) for i, f in enumerate(facts, 1))
            prompt = (
                f"Page: {page_url}\n\nComponents:\n{facts_block}\n\n"
                "Write the documentation entries."
            )
            try:
                narration = self.agent.generate(prompt, system_instruction=self.component_catalog_skill)
            except Exception as exc:  # noqa: BLE001 - degrade this one page, not the whole catalog
                narration = f"_(narration unavailable: {exc})_\n\nRaw facts:\n```\n{facts_block}\n```"
            sections.append(f"## {page_url}\n\n{narration}\n")
        if sections:
            write_output(
                self.components_catalog_file,
                "# Component Catalog\n\n" + "\n---\n\n".join(sections),
            )

    def _select_dna_components(self, components: list, states: dict) -> list:
        """Pick up to `batch_size` DNA components to show, prioritizing what's
        actually useful over raw DOM order.

        Regression fix: a mega-menu's items are commonly present in the DOM
        the whole time, just CSS-hidden until their trigger is
        clicked/hovered (see PlaywrightScraper._discover_components's
        `visible` field) - on a page with hundreds of components, they can
        sit far past `batch_size` in raw DOM order. Slicing DOM order alone
        meant clicking the trigger correctly revealed them in the browser but
        never actually surfaced them to the model, which then had nothing
        useful left to pick but the same trigger it had already clicked -
        stuck re-opening a menu it could never see inside of.

        Priority (stable sort - ties keep their original relative DOM order),
        from most to least useful to show right now: visible + never-shown-to-
        the-model-at-all; visible + shown-but-never-interacted-with; visible +
        interacted-with; then the same three bands again for invisible
        components. `visible` defaults to True when absent (e.g. scrapers/
        tests that don't report it), so this is a no-op (falls back to pure
        DOM order) unless the scraper actually knows.

        Two independent signals feed this, not one:
        - `interacted` (from `states`, this page's persisted component states
          in `graph_store` - see `_build_iteration_prompt`): has a click/fill/
          submit *actually* ever targeted this path, in this run or a
          previous one. Correctly deprioritizes a component acted on in a
          *previous run* against a persisted `graph_store` (neo4j, `fresh:
          false`) from turn one of a brand-new process - something the
          in-process `_shown_component_paths` set alone could never know.
        - `already_shown` (`_shown_component_paths`, this run only): has this
          path merely been *displayed* to the model before, regardless of
          whether it was ever acted on. Keeps the original mega-menu
          regression fix intact: a just-revealed item (never shown) must
          still outrank an already-displayed-but-unclicked filler element for
          a `component_batch_size` slot, which `interacted` alone can't
          express, since neither one has been interacted with yet.
        """
        def priority(comp: dict) -> tuple:
            visible = comp.get("visible", True)
            path = comp.get("path", "")
            interacted = states.get(path, {}).get("interacted", False)
            already_shown = path in self._shown_component_paths
            return (not visible, interacted, already_shown)

        return sorted(components, key=priority)[: self.component_batch_size]

    def _describe_dna_element(self, comp: dict, text: str, interacted: bool = False) -> str:
        """Render one Clickable-elements line: tag + text, plus only the extra
        signal needed to tell a fill target from a click target and, for a
        fill target, what it's actually *for* (type, placeholder, label,
        current value, required, disabled, interacted) - never the CSS path
        or class list (see `_build_iteration_prompt`'s docstring for why).

        `interacted` (from `graph_store`'s persisted component states - has *any*
        click/fill/submit ever targeted this exact path, on any past turn, in
        this run or a previous one) tells the model "you
        already did something here" the way `current value=` already does for
        a text field's own content, but for every component kind, not just
        fillable ones - a button carries no visible state of its own the way
        a filled input does, so without this a clicked button looks identical
        on the next turn to one that's never been touched.

        `label` (from an associated <label> - see
        PlaywrightScraper._discover_components) is shown whenever it adds
        information beyond what `placeholder`/`text` already say, since a
        text-input's placeholder is often absent even when a real label
        exists next to it - without it, the model has nothing to go on for
        what value to generate before calling fill (see
        static_docs.py's `text_field_values` topic for the fuller guidance).

        `value` (the field's *current* content) is what actually lets the
        model tell "I already filled this" from "this is still empty" just by
        looking at the list - without it, the only record of a previous fill
        was a separate "Value typed" line in the progress log the model never
        sees, so a field that already had the right value in it looked
        identical to one that didn't. `required` flags which fields actually
        block submission, vs. ones that don't need attention before clicking
        a submit button."""
        extras = []
        if comp.get("input_type"):
            extras.append(f'type="{comp["input_type"]}"')
        if comp.get("placeholder"):
            extras.append(f'placeholder="{comp["placeholder"]}"')
        label = comp.get("label", "")
        if label and label not in (comp.get("placeholder", ""), text):
            extras.append(f'label="{label}"')
        if comp.get("value"):
            extras.append(f'current value="{comp["value"][:40]}"')
        if comp.get("required"):
            extras.append("required")
        if comp.get("disabled"):
            extras.append("disabled")
        if interacted:
            extras.append("interacted")
        extra_str = f" ({', '.join(extras)})" if extras else ""
        return f"<{comp.get('tag')}> {text!r}{extra_str}"

    def _page_structure_line(self, shown_components: list) -> str:
        """Deterministic, always-shown hints about page-level *structure* -
        not just what each element is, but what they mean together.

        Unlike the `help` /static/* topics, this doesn't depend on the model
        remembering to ask for it - a real crawl kept typing search queries
        into a combobox's search box instead of clicking one of the options
        already visible right below it, and separately never clicked an
        obviously-present submit button after filling every field. Both are
        "page flow" mistakes no single element's own description can fix -
        they need a statement about the *set* of currently-shown elements.

        Detection is structural, not keyword/language-based, so this works
        the same on a Spanish-labelled site as an English one: `role=option`
        for the combobox case, `input_type == "submit"` for the submit case
        (a <button type="submit"> reports "submit" as its `input_type` here
        the same as an <input type="submit">, since PlaywrightScraper reads
        the `type` attribute off the element regardless of tag).

        The submit-readiness check deliberately does *not* gate on `required`
        - a real site (empanad.app) marks no field `required` in markup at all
        (pure client-side/React validation, `el.required` is false on every
        field), so that attribute is unusable here and everywhere like it.
        `value` (does this field currently show *anything*) is the one signal
        we can actually verify from the DOM regardless of how a site
        validates - and an unconditional "click submit" hint without it was
        actively wrong: a real crawl clicked submit as its *very first*
        action, with the name field still empty, because the hint didn't
        distinguish "a submit button exists" from "this form is actually
        ready."
        """
        lines = []
        if any(c.get("role") == "option" for c in shown_components):
            lines.append(
                "Some numbered elements below are already-visible selectable options "
                "(shown after opening a dropdown/combobox) - click one of them directly by its "
                "number. Only fill the nearby search box first if the one you want isn't listed yet."
            )
        # Grouped per enclosing <form> (comp["form"], see PlaywrightScraper._discover_components),
        # not whole-page: a page with two independent forms (e.g. newsletter signup +
        # contact form) must not treat "any submit button anywhere" as gating "any
        # unfilled field anywhere" - each form's own readiness is judged only against
        # its own fields. Components with no enclosing form (form == "") are grouped
        # together too, under the same "whole page" bucket the original single-form
        # check already covered.
        indexed = list(enumerate(shown_components, 1))
        forms = {}
        for idx, c in indexed:
            forms.setdefault(c.get("form", ""), []).append((idx, c))
        for form_key, entries in forms.items():
            submit = next((c for _, c in entries if c.get("input_type") == "submit"), None)
            if not submit:
                continue
            unfilled_refs = [
                idx
                for idx, c in entries
                if c.get("tag") in ("input", "textarea", "select")
                and c.get("role") != "option"
                and not c.get("value")
            ]
            if unfilled_refs:
                lines.append(
                    f"Do not click submit yet - field(s) {unfilled_refs} still show no current "
                    "value. Fill those first, then re-check this list before submitting."
                )
            else:
                label = (submit.get("text") or "").strip() or "the submit button"
                lines.append(
                    f'Every visible text field already shows a value - click submit ("{label}") '
                    "next instead of continuing to explore."
                )
        return ("\n".join(lines) + "\n") if lines else ""

    def _last_error_line(self) -> str:
        """Consume-once advisory line reporting why the previous iteration's
        action failed, if it did - see `_last_failed_action` in __init__ for
        why this feedback loop matters."""
        if not self._last_failed_action:
            return ""
        line = (
            f"Note: your last action ({self._last_failed_action}) failed: "
            f"{self._last_action_error}. Try something different.\n"
        )
        self._last_failed_action = None
        return line

    def _pending_guidance_line(self) -> str:
        """Consume-once line surfacing the last `help` lookup's answer, if any -
        same shape as `_last_error_line`, see `_pending_help_topic`/`_pending_help_text`
        in __init__ for why this is ephemeral rather than accumulated."""
        if not self._pending_help_topic:
            return ""
        line = f"Guidance ({self._pending_help_topic}): {self._pending_help_text}\n"
        self._pending_help_topic = None
        self._pending_help_text = None
        return line

    def _loop_signal_line(self, url: str) -> str:
        """Advisory prompt line naming components that already led to `url` before.

        Queried from the graph store every iteration (see `get_loop_signals`) -
        this is a warning, not a hard block: the model already can't re-GOTO a
        Finished page (see the guard in `_execute_loop`), but a CLICK that leads
        back to a page it's already reached via a different component is legal
        and sometimes correct, so we only inform, never override the model's
        choice (see wiki/graph-based-crawl-tracking.md).
        """
        signals = self.graph_store.get_loop_signals(self.base_domain, self._clean_url(url))
        if not signals:
            return ""
        tried = ", ".join(f'{s["component"]} (from {s["from"]})' for s in signals)
        return f"Note: this page has already been reached via: {tried}. Trying the same route again will not make progress.\n"

    def _component_debt_line(self, current_url: str) -> str:
        """Advisory prompt line naming pages left behind with real, un-interacted-
        with components still on them - the revisit queue.

        Deterministic and always-shown, per wiki/prompt-engineering-for-llm-
        agents.md Principle 6: without this, a component discovered on a page
        the agent has since navigated away from is invisible to every future
        prompt, since `_select_dna_components` only ever sees the *current*
        page's live DOM. Excludes `current_url` (that page's own unexplored
        components are already shown in this same prompt's Clickable elements
        list) and is informational only - the navigate-decline guard in
        `_execute_loop` is what actually makes a revisit possible, not this
        line; this just tells the model such a revisit exists and is worth it.

        `semantic_only=False`, matching `_reject_premature_finish` - this line
        must name the same debt that guard will actually enforce, library-built
        (cursor:pointer-only) components included, or it would tell the model
        "nothing left here" about a page that then goes on to block `finish`.

        Also excludes anything in `self._given_up_pages` - once
        `_reject_premature_finish` has stopped enforcing a page's debt (see
        `_apply_diminishing_returns`), pointing the model back at it here would
        just resume the same non-improving cycle that got it given up on.
        """
        debt_pages = [
            row
            for row in self.graph_store.get_pages_with_unexplored_components(
                self.base_domain, limit=self.pending_batch_size, semantic_only=False
            )
            if row["url"] != current_url and row["url"] not in self._given_up_pages
        ]
        if not debt_pages:
            return ""
        named = ", ".join(f'{row["url"]} ({row["unexplored_count"]})' for row in debt_pages)
        return (
            f"Pages you've already left with unexplored elements (navigate back to continue): "
            f"{named}\n"
        )

    def _handle_iteration_result(
        self,
        iter_num: int,
        action: AgentAction,
        from_url: str,
        state: PageState,
        before_components: Optional[list] = None,
    ) -> None:
        """Update state, progress, and the navigation graph after an iteration."""
        url = self._clean_url(state.url)
        component = self._describe_component(action, from_url)

        self._upsert(url, status="Finished", components=len(state.components))
        self._record_page_inventory(state)
        self._update_discovered_routes(state.links, source=url)
        self._record_description(url, state.description)
        self.graph_store.record_edge(
            self.base_domain, self._clean_url(from_url), url, component, action.raw
        )
        target_path = self._resolve_target_path(action)
        if target_path:
            self._record_component_interaction(from_url, target_path, action, state.url)
        # A click that reveals a set of listbox/menu options (a dropdown/combobox
        # opening) isn't knowable from a single snapshot - it's the *diff* between
        # what was on the page immediately before this click and immediately
        # after. Only meaningful in-place (state.url == from_url): a real
        # navigation's "before" page is a different page entirely, not a
        # revealed-in-place widget.
        if action.kind == "click" and target_path and before_components is not None and state.url == from_url:
            revealed = find_revealed_options(before_components, state.components)
            if revealed:
                self.graph_store.record_component_options(
                    self.base_domain, self._clean_url(from_url), target_path,
                    json.dumps({"kind": "combobox_trigger", "choices": revealed}),
                )
                # Each revealed option was already persisted as its own Component by
                # `_record_page_inventory` above (it's part of `state.components`) and
                # would otherwise count as its own unit of unexplored debt - meaning a
                # dropdown with a dozen choices (e.g. every empanada flavor) would
                # require clicking every single one before `finish` is allowed, on top
                # of the trigger itself. Tagging each one `excluded_from_debt=True`
                # keeps it discoverable/listable (and still shown in the ledger/catalog
                # via its own entry - see `_build_page_catalog_facts`'s
                # `revealed_option_member` handling) without requiring individual
                # interaction - interacting with the trigger that revealed the set
                # already counts as having explored the selector.
                for option in revealed:
                    option_path = option.get("path")
                    if not option_path:
                        continue
                    self.graph_store.record_component_options(
                        self.base_domain, self._clean_url(from_url), option_path,
                        json.dumps({"kind": "revealed_option_member", "trigger_path": target_path}),
                        excluded_from_debt=True,
                    )

        # `action.raw` is deliberately left showing the model's original, literal
        # output (useful for judging the model's own behavior) - but that means a
        # fill whose value got substituted by _execute_action's fallback (see its
        # docstring) would otherwise look, in this persisted log, identical to one
        # that filled nothing at all. This line is the visible record of what
        # actually reached the page.
        value_line = f'\nValue typed: "{action.value}"' if action.kind == "fill" else ""

        self._update_progress(
            f"ITERATION {iter_num}",
            f"From: {from_url}\nComponent: {component}\nAction: {action.raw}{value_line}\n"
            f"Now at: {state.url}\nComponents found: {len(state.components)}",
        )

    def _describe_component(self, action: AgentAction, from_url: str) -> str:
        """Best-effort human label for the link/element used to move to a new page.

        For a navigate action, this only claims a link if one was actually
        discovered on `from_url` pointing at the target (see
        `_update_discovered_routes` / `record_link`) - looking up a label by
        destination page alone was wrong whenever the same page had been
        linked to from multiple source pages with different anchor text,
        since it could attribute a link that exists on some other page
        entirely. For click/fill/submit, it's the tag/text of the numbered
        DNA element that was acted on.
        """
        if action.kind == "navigate":
            label = self.graph_store.get_link_label(
                self.base_domain, self._clean_url(from_url), self._clean_url(action.url or "")
            )
            if label and label != "-":
                return f'link "{label}"'
            return "direct navigation (no known link label)"
        if action.kind in ("click", "fill", "submit"):
            if action.ref is not None and action.ref in self._dna_index_map:
                comp = self._dna_index_map[action.ref]
                return f'<{comp["tag"]}> "{comp["text"]}"'
            return f"{action.kind} target {action.ref!r}"
        return ""

    def _execute_action(self, action: AgentAction) -> Optional[PageState]:
        """Execute the agent's chosen action.

        Returns None on failure; the actual error is stashed in
        `_last_action_error` so the caller can log *why* it failed, not just
        that it did (and so the next prompt can tell the model why, via
        `_last_error_line`).
        """
        self._last_action_error = None
        try:
            if action.kind == "navigate":
                return self.scraper.navigate(self._resolve_goto_url(action.url or ""))
            selector = self._resolve_ref_selector(action.ref)
            # Empty string ("") for the overwhelming common case (main page) - see
            # `_dna_index_map`'s comment. Only passed as a kwarg when non-empty, so
            # a scraper backend that doesn't accept `frame_url` (e.g. RestScraper,
            # or a test double) is unaffected for every component that isn't
            # actually inside an iframe - this stays fully backward compatible.
            frame_url = self._dna_index_map.get(action.ref, {}).get("frame_url", "")
            frame_kwargs = {"frame_url": frame_url} if frame_url else {}
            if action.kind == "click":
                return self.scraper.click(selector, **frame_kwargs)
            if action.kind == "fill":
                if not action.value:
                    # Observed in practice with native tool-calling on a small local
                    # model: it calls fill(ref) but either omits `value` entirely or
                    # supplies "" (see LocalAgent._parse_tool_call) - the model isn't
                    # reliably filling in real text either way. Filling "" every time
                    # is worse than useless: it looks like progress (a real action
                    # ran, a new PageState came back) while never actually submitting
                    # anything, which is exactly the infinite click-toggle/fill-empty
                    # loop this is fixing. Synthesizing a plausible value from the
                    # field's own metadata (see _generate_field_value) keeps the run
                    # moving forward instead of stalling on a silently-empty fill.
                    #
                    # Mutated onto `action` itself (not just a local variable) so
                    # every downstream consumer of `action.value` - _handle_iteration_
                    # result's logged details included - reflects what was actually
                    # typed, not the model's original (possibly empty) request. Without
                    # this, the persisted log kept showing the model's raw '"value": ""'
                    # with no visible sign a fallback ever ran, which read as "nothing
                    # happened" even when it had.
                    comp = self._dna_index_map.get(action.ref, {})
                    action.value = self._generate_field_value(comp)
                    print(f"fill {action.ref}: no value supplied, using generated fallback {action.value!r}")
                return self.scraper.fill(selector, action.value, **frame_kwargs)
            if action.kind == "submit":
                return self.scraper.submit(selector, **frame_kwargs)
        except Exception as exc:
            self._last_action_error = str(exc)
            print(f"Action failed: {exc}")
        return None

    @staticmethod
    def _generate_field_value(comp: dict) -> str:
        """Synthesize a plausible fill value from a component's own metadata, for when
        the model's fill action didn't supply one (see `_execute_action`).

        Same heuristics the `text_field_values` /static/* doc teaches the model to
        apply itself (src/api_server/static_docs.py) - this is the deterministic,
        code-side fallback for when the model doesn't (or can't reliably) do that
        itself, not a replacement for giving it that guidance.

        Keyword matching isn't English-only: a real run against a Spanish-labelled
        site (label="Correo electrónico") fell through to the generic default
        because "email" never appears - accents are stripped before matching and a
        few common Spanish equivalents are included per category, on the assumption
        that most sites this tool crawls won't be English-only.
        """
        input_type = (comp.get("input_type") or "").lower()
        hint = " ".join((comp.get(key) or "") for key in ("label", "placeholder", "name"))
        hint = unicodedata.normalize("NFKD", hint).encode("ascii", "ignore").decode("ascii").lower()

        def matches(*keywords: str) -> bool:
            return any(kw in hint for kw in keywords)

        if input_type == "email" or matches("email", "correo"):
            return "test@example.com"
        if input_type in ("tel", "phone") or matches("phone", "telefono", "celular"):
            return "555-0100"
        if input_type == "password" or matches("password", "contrasena", "clave"):
            return "TestPass123!"
        if input_type == "number" or matches("number", "numero", "cantidad"):
            return "1"
        if input_type == "url" or matches("website", "sitio web", "pagina web"):
            return "https://example.com"
        if input_type == "search" or matches("search", "buscar", "busqueda"):
            return "test"
        if matches("name", "nombre"):
            return "Test User"
        return "Test"

    def _resolve_goto_url(self, target: str) -> str:
        """Turn a navigate target into an absolute, navigable URL.

        The Pending routes shown to the model are scheme-stripped graph-node
        keys (see `_clean_url` - scheme is dropped so http/https variants of
        the same page count as one node), so the model naturally echoes back
        a schemeless url like "example.com/about" when it picks one. A real
        navigation needs an absolute URL, so default to https:// when the
        model's target has no scheme - a bare model target with a scheme
        (e.g. it invented a different absolute URL) is left untouched.
        """
        target = target.strip()
        if target.startswith(("http://", "https://")):
            return target
        return f"https://{target}"

    def _resolve_ref_selector(self, ref: Optional[int]) -> str:
        """Turn a click/fill/submit element ref (a number from the last
        Clickable-elements list) into the real Playwright selector.

        Unlike the legacy protocol, there is no literal-CSS-path or
        text-match fallback here - the model is only ever shown numbered
        refs and told to use them (see `_describe_dna_element` /
        `_tool_block_text`), so an unresolvable ref means the model
        hallucinated one and should be told so via the error-feedback loop
        rather than silently guessing at a selector on its behalf.
        """
        if ref is not None and ref in self._dna_index_map:
            return self._dna_index_map[ref]["path"]
        raise ValueError(f"Unknown element ref: {ref!r} - use a number from the Clickable elements list")

    def _write_graph_log(self) -> None:
        """Write the navigation graph (which action led from which page to which page).

        Written as JSON (queryable/machine-readable) to `graph_log_file`, and as
        a Mermaid flowchart appended to `progress_log_file` for immediate human
        visualization (renders automatically in GitHub/VS Code markdown preview).
        Read from the graph store (the source of truth) rather than any
        in-memory list, so this reflects whatever backend is configured.
        """
        edges = self.graph_store.get_edges(self.base_domain)
        if self.graph_log_file:
            write_output(self.graph_log_file, json.dumps(edges, indent=2))
        if self.progress_log_file and edges:
            append_output(
                self.progress_log_file,
                f"## NAVIGATION GRAPH\n\n{self._build_mermaid_graph(edges)}\n\n---\n\n",
            )

    def _build_mermaid_graph(self, edges: list) -> str:
        """Render `edges` as a Mermaid flowchart (nodes = pages, edges = the component
        used to get there - falls back to the raw action text if no component is known)."""
        node_ids: dict = {}

        def node_id(node_url: str) -> str:
            if node_url not in node_ids:
                node_ids[node_url] = f"n{len(node_ids)}"
            return node_ids[node_url]

        lines = ["```mermaid", "flowchart LR"]
        for edge in edges:
            src, dst = node_id(edge["from"]), node_id(edge["to"])
            label = (edge.get("component") or edge["action"]).replace('"', "'")[:40]
            lines.append(f'    {src}["{edge["from"]}"] -->|"{label}"| {dst}["{edge["to"]}"]')
        lines.append("```")
        return "\n".join(lines)

    def _synthesize_tree_report(self) -> str:
        """Synthesize final report using the DOM-Mapper skill."""
        try:
            path = pathlib.Path(self.progress_file)
            progress = path.read_text(encoding="utf-8")
            # Aggressive truncation for context window safety (8k chars ~ 2k tokens)
            if len(progress) > 8000:
                progress = "...(truncated)...\n" + progress[-8000:]

            prompt = (
                f"Full Research Log:\n{progress}\n\n"
                "Generate a Hierarchical System Mind-Map from this data."
            )
            return self.agent.generate(prompt, system_instruction=self.dom_mapper_skill)
        finally:
            self.scraper.close()
            self.graph_store.close()
