"""Phase 5 of the crawl4ai migration: post-hoc PRD synthesis from `GraphStore`.

With Neo4j (or `InMemoryGraphStore`) as the crawl's primary source of truth
(Phase 3), this is the step that reads it back and produces the final
markdown blueprint - the same output artifact `SimplePRDGenerator.generate_prd`
produced, but sourced entirely from persisted graph state rather than an
in-process research log. Runs independently of any live crawl: given a
`site` whose graph was populated by an earlier `MechanicalCrawler` run (or
even one from hours/days ago against a persisted Neo4j store), `synthesize()`
needs nothing else.

Three-stage map-reduce synthesis - not the two-stage shape this module used
to have. **Update - the original two-stage design (per-page narration, then
one single aggregate call over every page) turned out to be exactly the
unbounded-prompt bug wiki/local-and-small-model-constraints.md already
warned about, just never ported here from the now-deleted
`SimplePRDGenerator`'s `batch_size`-capped prompt construction:** confirmed
live on empanad.app (see docs/explicativos/avance-corridas-gemma-empanadapp.md)
- the single final `agent.generate()` call, built from every page's full
narrated component catalog plus the entire Mermaid navigation graph with no
size cap at all, hit `finish_reason: "length"` 4/4 times even at
`max_tokens: 8192`, crashing the whole run with zero `docs/` output despite
the crawl itself completing successfully every time. Now: **map** (one
bounded call per page, unchanged), **batch-summarize** (one bounded call per
`batch_size`-sized group of pages, producing a short section summary), then
**reduce** (one small final call over only the already-condensed section
summaries, never the raw per-page facts again - bounded regardless of site
size). The Mermaid graph is rendered deterministically and appended to the
output in code, never asked of the model - `build_mermaid_graph` already
does this without an LLM call, so asking the model to reproduce it verbatim
inside its own completion only spent real output-token budget on exactly the
highest-risk call for nothing.

Each stage gets its own system_instruction, per
wiki/prompt-engineering-for-llm-agents.md Principle 1 - none are shared with
each other or with the fill-value call (Phase 4).
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.interfaces import Agent, GraphStore
from .component_classifier import describe_options

CATALOG_SYSTEM_INSTRUCTION = (
    "You are documenting the interactive components found on one page of a web application, from "
    "a deterministic list of facts about each one (type, text/label, current state). Write a short, "
    "readable Markdown description for each component - what it is and what it does - grouped "
    "sensibly if there are many. Do not invent facts not present in the list. Do not mention CSS "
    "selectors, DOM paths, or any implementation detail - describe the component the way a person "
    "looking at the rendered page would."
)

# Used by the batch-summarize stage: summarizes one bounded group of pages'
# facts into a short section. Kept under its original name (still imported by
# existing tests/callers) even though its job shifted from "summarize every
# page in the site" to "summarize one batch of pages" - the actual prose below
# describes the batch-scoped job now.
SYNTHESIS_SYSTEM_INSTRUCTION = (
    "You are documenting one section of a larger web application - a group of pages, each with its "
    "route, description, and already-documented components - as part of a Digital Blueprint. Write a "
    "short, readable Markdown section summarizing what these pages do and how they fit together. Do "
    "not invent pages, routes, or components not present in the provided data."
)

# Used by the reduce stage: combines several already-condensed section
# summaries (never raw per-page facts) into the Blueprint's overall narrative.
# Deliberately its own instruction, not shared with SYNTHESIS_SYSTEM_INSTRUCTION
# above - "summarize condensed summaries" is a structurally different task from
# "summarize raw facts," per wiki/prompt-engineering-for-llm-agents.md Principle 1.
REDUCE_SYSTEM_INSTRUCTION = (
    "You are producing the overview narrative of a Digital Blueprint: a Markdown document describing "
    "a web application's structure for someone who has never seen it, from several already-condensed "
    "section summaries (not raw page data) covering different parts of the application. Combine them "
    "into one coherent hierarchical overview - explain what the application does overall, then how its "
    "sections/flows relate and how a user moves between them. Do not restate the summaries verbatim; "
    "synthesize them. Do not invent pages, routes, or components not present in the provided summaries."
)


def _build_page_facts(page_components: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One catalog-ready fact dict per distinct control on a page, collapsing
    a stepper's increment/decrement/value trio or a choice-group's N members
    into a single entry - matches the `options` JSON shape
    `GraphStoreSink.record_inventory` actually persists (Phase 3), not the
    older `SimplePRDGenerator._build_page_catalog_facts`'s schema, since the
    two were never the same data source (see this module's docstring).

    The three-shape `options` disambiguation itself lives in
    `component_classifier.py::describe_options` - shared with
    `component_tree.py`'s deterministic renderer (Phase 5) rather than
    duplicated. `revealed_options` (Phase 1's dropdown-variant capture) has
    no branch here - it falls through to the generic case below, unchanged
    from before this field existed - `component_tree.py` is where revealed
    options actually get surfaced; this function's job is narration text,
    not a full inventory of every options shape.
    """
    facts: List[Dict[str, Any]] = []
    seen_stepper_containers = set()
    seen_choice_groups = set()
    for path in sorted(page_components.keys()):
        record = page_components[path]
        parsed = describe_options(record.get("options") or "")

        if parsed and parsed["kind"] == "stepper":
            container = parsed.get("container") or path
            if container in seen_stepper_containers:
                continue
            seen_stepper_containers.add(container)
            facts.append(
                {
                    "type": "stepper control (increment/decrement)",
                    "text": record.get("text") or "quantity control",
                    "current_value": parsed.get("current_value"),
                    "interacted": bool(record.get("interacted")),
                }
            )
            continue

        if parsed and parsed["kind"] == "choice_group":
            group = parsed["group"]
            if group in seen_choice_groups:
                continue
            seen_choice_groups.add(group)
            facts.append(
                {
                    "type": "radio/checkbox group",
                    "text": f"group '{group}'",
                    "choices": [c["text"] for c in parsed["choices"] if c.get("text")],
                    "interacted": bool(record.get("interacted")),
                }
            )
            continue

        text = record.get("text") or "(no accessible label found on this element)"
        facts.append(
            {
                "type": record.get("component_type") or "element",
                "text": text,
                "interacted": bool(record.get("interacted")),
            }
        )
    return facts


def _render_fact_line(index: int, fact: Dict[str, Any]) -> str:
    parts = [f"type={fact['type']!r}", f"text={fact.get('text', '')!r}", f"interacted={fact.get('interacted')}"]
    if "current_value" in fact:
        parts.append(f"current_value={fact['current_value']!r}")
    if "choices" in fact:
        parts.append(f"choices={fact['choices']!r}")
    return f"{index}. " + " ".join(parts)


def build_mermaid_graph(edges: List[Dict[str, str]]) -> str:
    """Render `edges` ({from, component, action, to}) as a Mermaid flowchart -
    ported unchanged from `SimplePRDGenerator._build_mermaid_graph`, a pure
    function with no dependency on the old class's internals.
    """
    node_ids: Dict[str, str] = {}

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


class GraphPRDSynthesizer:
    """Reads `site`'s crawl graph and produces the final PRD markdown -
    writes nothing back to `GraphStore`, the inverse of `MechanicalCrawler`.
    """

    def __init__(self, agent: Agent, graph_store: GraphStore, batch_size: int = 5) -> None:
        self.agent = agent
        self.graph_store = graph_store
        # Pages per batch-summarize call (see `_summarize_batches`). Default kept
        # small deliberately: each "item" here is a full page block including its
        # already-narrated component catalog - much heavier per item than a short
        # label, so this is a more conservative budget than a typical crawl-time
        # batch_size knob. See this module's docstring for why this exists at all.
        self.batch_size = batch_size

    def _narrate_page_catalog(self, site: str) -> Dict[str, str]:
        """One `agent.generate()` call per page (batched across all of that
        page's components, not one call per component - same small-model-
        conscious discipline wiki/local-and-small-model-constraints.md
        established). A narration failure on one page degrades to its raw
        facts rather than aborting the whole catalog - documentation
        enrichment, not something correctness depends on.
        """
        ledger = self.graph_store.get_component_ledger(site)
        narrations: Dict[str, str] = {}
        for page_url in sorted(ledger.keys()):
            facts = _build_page_facts(ledger[page_url])
            if not facts:
                continue
            facts_block = "\n".join(_render_fact_line(i, f) for i, f in enumerate(facts, 1))
            prompt = f"Page: {page_url}\n\nComponents:\n{facts_block}\n\nWrite the documentation entries."
            try:
                narrations[page_url] = self.agent.generate(prompt, system_instruction=CATALOG_SYSTEM_INSTRUCTION)
            except Exception as exc:  # noqa: BLE001 - degrade this one page, not the whole catalog
                narrations[page_url] = f"_(narration unavailable: {exc})_\n\nRaw facts:\n```\n{facts_block}\n```"
        return narrations

    @staticmethod
    def _build_page_lines(rows: List[Dict[str, Any]], descriptions: Dict[str, str], catalog: Dict[str, str]) -> List[str]:
        """One text block per page - route/status/component-count, its
        recorded description, and its narrated component catalog if any.
        Extracted unchanged from the old single-prompt `synthesize` so both
        `_summarize_batches` and any future caller share one construction.
        """
        page_lines = []
        for row in rows:
            url = row["url"]
            line = f"- {url} [{row['status']}, {row['components']} components]"
            if descriptions.get(url):
                line += f"\n  Description: {descriptions[url]}"
            if catalog.get(url):
                line += f"\n  Components:\n{catalog[url]}"
            page_lines.append(line)
        return page_lines

    def _summarize_batches(self, site: str, page_lines: List[str]) -> List[str]:
        """Group `page_lines` into `self.batch_size`-sized chunks and produce
        one bounded `agent.generate()` call per chunk - the fix for the
        unbounded "every page in one prompt" call this module used to make
        (see this module's docstring). A batch failure degrades to its raw
        page lines rather than aborting the whole run, matching
        `_narrate_page_catalog`'s existing degrade-not-abort discipline.
        """
        batches = [page_lines[i : i + self.batch_size] for i in range(0, len(page_lines), self.batch_size)]
        summaries: List[str] = []
        for batch in batches:
            batch_block = "\n".join(batch)
            prompt = (
                f"Site: {site}\n\n"
                f"Pages in this section ({len(batch)}):\n{batch_block}\n\n"
                "Write the section summary."
            )
            try:
                summaries.append(self.agent.generate(prompt, system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION))
            except Exception as exc:  # noqa: BLE001 - degrade this one batch, not the whole run
                summaries.append(f"_(section summary unavailable: {exc})_\n\n{batch_block}")
        return summaries

    def _reduce(self, site: str, section_summaries: List[str]) -> str:
        """Combine already-condensed section summaries into the Blueprint's
        overview narrative - one small call, bounded regardless of site size
        since it never sees raw per-page facts, only the summaries above.
        Degrades to a plain concatenation under simple headers on failure,
        rather than crashing the whole run and writing zero output (the
        actual empanad.app symptom this module's docstring describes).
        """
        prompt = (
            f"Site: {site}\n\n"
            f"Section summaries ({len(section_summaries)}):\n\n" + "\n\n---\n\n".join(section_summaries) + "\n\n"
            "Write the overview narrative."
        )
        try:
            return self.agent.generate(prompt, system_instruction=REDUCE_SYSTEM_INSTRUCTION)
        except Exception as exc:  # noqa: BLE001 - degrade to raw sections, don't abort the run
            headers = (f"## Section {i}\n\n{s}" for i, s in enumerate(section_summaries, 1))
            return f"_(overview synthesis unavailable: {exc})_\n\n" + "\n\n".join(headers)

    def synthesize(self, site: str) -> str:
        """Produce the final PRD markdown for `site` - the only method
        callers need. Reads, in order: the page/route table, the navigation
        edges, per-page component narrations (derived from the ledger), and
        recorded page descriptions - then a bounded map-reduce pass (batch-
        summarize, then reduce) over the aggregate. See this module's
        docstring for why this replaced the old single unbounded call.
        """
        rows = self.graph_store.get_progress_table_rows(site)
        edges = self.graph_store.get_edges(site)
        descriptions = self.graph_store.get_page_descriptions(site)
        catalog = self._narrate_page_catalog(site)

        page_lines = self._build_page_lines(rows, descriptions, catalog)
        section_summaries = self._summarize_batches(site, page_lines)
        overview = self._reduce(site, section_summaries)

        # Rendered deterministically, never asked of the model - see this
        # module's docstring for why this used to cost real output-token
        # budget on the highest-risk call for no reason.
        mermaid = build_mermaid_graph(edges)
        return f"{overview}\n\n## Navigation Graph\n\n{mermaid}\n"
