"""
PRD Generator implementation using a planned, multi-skill autonomous loop.
"""
from __future__ import annotations

import json
import pathlib
from typing import Optional

from ..core.interfaces import Action, Agent, GraphStore, PageState, PRDGenerator, Scraper, parse_action
from ..core.registry import GENERATOR_REGISTRY
from ..storage.memory_graph_store import InMemoryGraphStore
from ..utils.io import append_output, write_output

# Applied only to the per-iteration decision call, never to _create_plan (which
# needs to produce a multi-step narrative, not a single command) - reusing the
# same system_instruction for both previously caused the model to collapse its
# plan into a single GOTO line.
_DECISION_FORMAT_INSTRUCTION = (
    "Respond with EXACTLY ONE line: `GOTO <url>`, `CLICK <element number>`, or `FINISH`. "
    "For CLICK, use the number shown in brackets next to the element in the list below "
    "(e.g. `CLICK 3`) - do not invent a CSS path. "
    "No explanations, no markdown, no other text before or after the command."
)


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
        max_iterations: int = 12,
        batch_size: int = 20,
    ) -> None:
        """Initialize with brain (agent), hands (scraper), and progress tracker.

        Args:
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
            batch_size: Max pending routes and DNA components sent per iteration
                prompt. Smaller values mean faster, cheaper iterations at the
                cost of needing more of them (raise max_iterations to match) to
                work through a large site - useful for slow/small local models.
        """
        self.agent = agent
        self.scraper = scraper
        self.graph_store = graph_store or InMemoryGraphStore()
        self.progress_file = progress_file
        self.progress_log_file = progress_log_file
        self.graph_log_file = graph_log_file
        self.max_iterations = max_iterations
        self.batch_size = batch_size
        # Load specialized skills. Note: PROGRESS.md is written mechanically by
        # _update_progress() below - the LLM is never asked to author it, so the
        # "archaeology-progress-tracker" skill is intentionally not loaded/used
        # as a system_instruction (it previously was, and its "update PROGRESS.md
        # with a table" instructions conflicted with the GOTO/CLICK/FINISH format
        # expected during the decision loop, causing the model to emit progress
        # tables instead of actions).
        self.archeologist_skill = self._load_skill("archeologist-skill")
        self.dom_mapper_skill = self._load_skill("dom-mapper-skill")

        # Track discovery state. The graph itself (pages/edges) lives in
        # self.graph_store, not here - self.base_domain doubles as the "site"
        # key used to scope every graph_store call.
        self.base_domain: Optional[str] = None
        self.plan_summary: str = ""
        self._last_action_error: Optional[str] = None
        self._dna_index_map: dict = {}

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
        self._update_discovered_routes(state.links, source=url)
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
        """Normalize a URL into a graph-node key: drop fragment, trailing slash, and scheme.

        A route discovered via an http:// link almost always redirects to
        https:// (or vice versa) - without stripping the scheme, the two
        variants were treated as distinct graph nodes, so visiting one via its
        canonical form never marked the other "Finished". The crawler would
        then ping-pong between the http:// and https:// variants of the exact
        same page indefinitely, since both kept showing up as "Pending".
        """
        cleaned = url.split("#")[0].rstrip("/")
        for prefix in ("https://", "http://"):
            if cleaned.startswith(prefix):
                return cleaned[len(prefix):]
        return cleaned

    def _upsert(self, url: str, status: str = "Pending", components: int = 0, context: str = "", label: str = "") -> None:
        """Normalize a URL into its graph-node key and upsert it into the graph store."""
        self.graph_store.upsert_page(
            self.base_domain, self._clean_url(url), status=status, components=components,
            context=context, label=label,
        )

    def _update_discovered_routes(self, links: list, source: str) -> None:
        """Add new same-domain links to discovery list."""
        for link in links:
            href = link.get("href", "")
            if href and self._get_domain(href) == self.base_domain:
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

    def _create_plan(self, state: PageState) -> str:
        """Create a step-by-step research plan for deep excavation."""
        pending = self.graph_store.get_pending(self.base_domain)
        shown = pending[: self.batch_size]
        prompt = (
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
        content = f"{header}{table}\n\n## Log: {stage}\n\n{details}\n\n---\n"
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

    def _execute_loop(self, state: PageState) -> None:
        """The core iteration loop for deep component discovery.

        A malformed or failed action skips that iteration rather than aborting
        the whole run - a single bad response from a flaky/small model, or one
        failed click, shouldn't cut a run short after visiting only a handful
        of the discovered routes. The agent decides every iteration; the engine
        doesn't second-guess or override its choices, only records outcomes -
        see PlaywrightScraper.click() for why click failures now surface here
        as a genuine failure instead of a silent, indistinguishable no-op.
        """
        current_state = state
        for i in range(self.max_iterations):
            print(f"Research Iteration {i+1}...")
            from_url = current_state.url

            prompt = self._build_iteration_prompt(current_state)
            system_instruction = f"{self.archeologist_skill}\n\n{_DECISION_FORMAT_INSTRUCTION}"
            decision = self.agent.generate(prompt, system_instruction=system_instruction).strip()
            print(f"Action: {decision}")

            action = parse_action(decision)
            if action.kind == "finish":
                self._update_progress(f"ITERATION {i+1}", "Agent concluded research.")
                break

            if action.kind == "unknown":
                print("Warning: response was not a valid GOTO/CLICK/FINISH action, skipping.")
                self._update_progress(
                    f"ITERATION {i+1}",
                    f"Agent response was not a valid action (ignored):\n{decision[:500]}",
                )
                continue

            # Graph-traversal guard: refuse to re-navigate to an already-visited
            # node. This is a cheap, explicit check (no page load spent) on top
            # of the "Pending" list already excluding visited routes - it's the
            # safety net for cases like scheme (http/https) duplicates or the
            # model simply not following instructions.
            if action.kind == "goto" and self._already_visited(action.target):
                node = self._clean_url(action.target)
                print(f"Already visited {node}, skipping re-navigation.")
                self._update_progress(
                    f"ITERATION {i+1}",
                    f"GOTO {action.target} skipped: {node} is already visited in the graph.",
                )
                continue

            next_state = self._execute_action(decision)
            if next_state is None:
                reason = f" Reason: {self._last_action_error}" if self._last_action_error else ""
                print(f"Warning: action did not produce a new page state, skipping.{reason}")
                self._update_progress(
                    f"ITERATION {i+1}",
                    f"Action failed to produce a new page state (ignored):\n{decision}\n{reason}",
                )
                continue

            self._handle_iteration_result(i + 1, decision, from_url, next_state)
            current_state = next_state

    def _already_visited(self, url: str) -> bool:
        """Whether a URL is already a Finished node in the navigation graph."""
        return self.graph_store.is_visited(self.base_domain, self._clean_url(url))

    def _build_iteration_prompt(self, state: PageState) -> str:
        """Build a bounded prompt for a single discovery iteration.

        Pending routes and page DNA are capped at `batch_size` each, so a single
        iteration's prompt (and inference time) stays roughly constant no matter
        how large the site is - the tradeoff is needing more iterations to work
        through everything. DNA elements are shown as a short numbered list (tag
        + text only, no CSS path or attributes.class) and CLICK refers to them by
        number - the full path/class list used to be dumped verbatim per element,
        which on CSS-framework-heavy sites can be hundreds of characters each and
        was likely the single biggest driver of prompt size (and inference time).
        """
        pending = self.graph_store.get_pending(self.base_domain)
        shown_pending = pending[: self.batch_size]
        shown_components = state.components[: self.batch_size]

        self._dna_index_map = {}
        dna_lines = []
        for idx, comp in enumerate(shown_components, 1):
            text = (comp.get("text") or "").strip()[:60]
            self._dna_index_map[idx] = {
                "path": comp.get("path", ""),
                "tag": comp.get("tag", ""),
                "text": text,
            }
            dna_lines.append(f"[{idx}] <{comp.get('tag')}> {text!r}")
        dna_block = "\n".join(dna_lines) if dna_lines else "(none)"

        plan_line = f"Plan: {self.plan_summary}\n" if self.plan_summary else ""
        loop_line = self._loop_signal_line(state.url)

        return (
            f"{plan_line}"
            f"You are currently at: {state.url} (already visited - do NOT GOTO this URL again)\n"
            f"{loop_line}"
            f"Pending routes you may GOTO ({len(shown_pending)} of {len(pending)} shown): "
            f"{json.dumps(shown_pending)}\n"
            f"Clickable elements on this page, for CLICK targets ({len(shown_components)} of "
            f"{len(state.components)} shown):\n{dna_block}\n\n"
            "Action: GOTO <one of the Pending routes above>, CLICK <element number from the list "
            "above>, or FINISH."
        )

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

    def _handle_iteration_result(
        self, iter_num: int, action_text: str, from_url: str, state: PageState
    ) -> None:
        """Update state, progress, and the navigation graph after an iteration."""
        url = self._clean_url(state.url)
        component = self._describe_component(parse_action(action_text), from_url)

        self._upsert(url, status="Finished", components=len(state.components))
        self._update_discovered_routes(state.links, source=url)
        self.graph_store.record_edge(
            self.base_domain, self._clean_url(from_url), url, component, action_text
        )

        self._update_progress(
            f"ITERATION {iter_num}",
            f"From: {from_url}\nComponent: {component}\nAction: {action_text}\n"
            f"Now at: {state.url}\nComponents found: {len(state.components)}",
        )

    def _describe_component(self, action: Action, from_url: str) -> str:
        """Best-effort human label for the link/element used to move to a new page.

        For GOTO, this only claims a link if one was actually discovered on
        `from_url` pointing at the target (see `_update_discovered_routes` /
        `record_link`) - looking up a label by destination page alone was
        wrong whenever the same page had been linked to from multiple source
        pages with different anchor text, since it could attribute a link
        that exists on some other page entirely. For CLICK, it's the tag/text
        of the numbered DNA element that was clicked.
        """
        if action.kind == "goto":
            label = self.graph_store.get_link_label(
                self.base_domain, self._clean_url(from_url), self._clean_url(action.target)
            )
            if label and label != "-":
                return f'link "{label}"'
            return "direct navigation (no known link label)"
        if action.kind == "click":
            target = action.target.strip()
            if target.isdigit() and int(target) in self._dna_index_map:
                comp = self._dna_index_map[int(target)]
                return f'<{comp["tag"]}> "{comp["text"]}"'
            return f"click target {action.target!r}"
        return ""

    def _execute_action(self, decision: str) -> Optional[PageState]:
        """Execute the agent's chosen action.

        Returns None on failure; the actual error is stashed in
        `_last_action_error` so the caller can log *why* it failed, not just
        that it did.
        """
        self._last_action_error = None
        action = parse_action(decision)
        try:
            if action.kind == "goto":
                return self.scraper.navigate(self._resolve_goto_url(action.target))
            if action.kind == "click":
                return self.scraper.click(self._resolve_click_selector(action.target))
        except Exception as exc:
            self._last_action_error = str(exc)
            print(f"Action failed: {exc}")
        return None

    def _resolve_goto_url(self, target: str) -> str:
        """Turn a GOTO target into an absolute, navigable URL.

        The Pending routes shown to the model are scheme-stripped graph-node
        keys (see `_clean_url` - scheme is dropped so http/https variants of
        the same page count as one node), so the model naturally echoes back
        a schemeless url like "example.com/about" when it picks one. A real
        navigation needs an absolute URL, so default to https:// when the
        model's target has no scheme - a bare model target with a scheme
        (e.g. it invented a different absolute URL) is left untouched.
        """
        target = target.strip()
        if target.startswith("http://") or target.startswith("https://"):
            return target
        return f"https://{target}"

    def _resolve_click_selector(self, target: str) -> str:
        """Turn a CLICK target into a Playwright selector.

        Preferred: a bare number referring to the numbered DNA list shown in
        the last iteration prompt (cheap - no CSS path for the model to
        reproduce). Falls back to treating the target as a literal CSS path,
        or as visible text to match, for models that don't follow the
        numbered format.
        """
        target = target.strip()
        if target.isdigit() and int(target) in self._dna_index_map:
            return self._dna_index_map[int(target)]["path"]
        if any(c in target for c in (">", "#", ".")):
            return target
        return f"text='{target}'"

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
