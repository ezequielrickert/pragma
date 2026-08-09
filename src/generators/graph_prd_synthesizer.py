"""Phase 5 of the crawl4ai migration: post-hoc PRD synthesis from `GraphStore`.

With Neo4j (or `InMemoryGraphStore`) as the crawl's primary source of truth
(Phase 3), this is the step that reads it back and produces the final
markdown blueprint - the same output artifact `SimplePRDGenerator.generate_prd`
produced, but sourced entirely from persisted graph state rather than an
in-process research log. Runs independently of any live crawl: given a
`site` whose graph was populated by an earlier `MechanicalCrawler` run (or
even one from hours/days ago against a persisted Neo4j store), `synthesize()`
needs nothing else.

Two-stage synthesis, the same *shape* `SimplePRDGenerator._write_component_catalog`
+ `_synthesize_tree_report` already used (per-page narration batched into one
`agent.generate()` call each, then one final call over the aggregate) - not a
literal port, since the input here is four `GraphStore` queries, not an
accumulated markdown string. Each stage gets its own system_instruction, per
wiki/prompt-engineering-for-llm-agents.md Principle 1 - neither is shared with
the fill-value call (Phase 4) or with each other.
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

SYNTHESIS_SYSTEM_INSTRUCTION = (
    "You are producing a Digital Blueprint: a Markdown document describing a web application's "
    "structure for someone who has never seen it, from a structured summary of every page crawled "
    "(its route, description, and documented components) and the navigation graph connecting them. "
    "Produce a hierarchical overview - group related pages/flows, explain what the application does "
    "overall, then describe each significant page/section and how a user moves between them. Include "
    "the provided Mermaid flowchart verbatim in an appropriate section. Do not invent pages, routes, "
    "or components not present in the provided data."
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

    def __init__(self, agent: Agent, graph_store: GraphStore) -> None:
        self.agent = agent
        self.graph_store = graph_store

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

    def synthesize(self, site: str) -> str:
        """Produce the final PRD markdown for `site` - the only method
        callers need. Reads, in order: the page/route table, the navigation
        edges, per-page component narrations (derived from the ledger), and
        recorded page descriptions - then one final `agent.generate()` call
        over their aggregate.
        """
        rows = self.graph_store.get_progress_table_rows(site)
        edges = self.graph_store.get_edges(site)
        descriptions = self.graph_store.get_page_descriptions(site)
        catalog = self._narrate_page_catalog(site)

        page_lines = []
        for row in rows:
            url = row["url"]
            line = f"- {url} [{row['status']}, {row['components']} components]"
            if descriptions.get(url):
                line += f"\n  Description: {descriptions[url]}"
            if catalog.get(url):
                line += f"\n  Components:\n{catalog[url]}"
            page_lines.append(line)

        mermaid = build_mermaid_graph(edges)

        prompt = (
            f"Site: {site}\n\n"
            f"Pages ({len(rows)}):\n" + "\n".join(page_lines) + "\n\n"
            f"Navigation graph:\n{mermaid}\n\n"
            "Generate the Digital Blueprint."
        )
        return self.agent.generate(prompt, system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION)
