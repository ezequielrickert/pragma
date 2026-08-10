"""Post-hoc PRD synthesis from `GraphStore`: map, batch-summarize, reduce.
Details: docs/dev/generators/graph_prd_synthesizer.md#module
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

# Batch-summarize stage: one bounded group of pages' facts into a short section.
# Details: docs/dev/generators/graph_prd_synthesizer.md#synthesis_system_instruction
SYNTHESIS_SYSTEM_INSTRUCTION = (
    "You are documenting one section of a larger web application - a group of pages, each with its "
    "route, description, and already-documented components - as part of a Digital Blueprint. Write a "
    "short, readable Markdown section summarizing what these pages do and how they fit together. Do "
    "not invent pages, routes, or components not present in the provided data."
)

# Reduce stage: combines already-condensed section summaries, never raw facts.
# Details: docs/dev/generators/graph_prd_synthesizer.md#reduce_system_instruction
REDUCE_SYSTEM_INSTRUCTION = (
    "You are producing the overview narrative of a Digital Blueprint: a Markdown document describing "
    "a web application's structure for someone who has never seen it, from several already-condensed "
    "section summaries (not raw page data) covering different parts of the application. Combine them "
    "into one coherent hierarchical overview - explain what the application does overall, then how its "
    "sections/flows relate and how a user moves between them. Do not restate the summaries verbatim; "
    "synthesize them. Do not invent pages, routes, or components not present in the provided summaries."
)


def _build_page_facts(page_components: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One catalog-ready fact dict per distinct control on a page.
    Details: docs/dev/generators/graph_prd_synthesizer.md#_build_page_facts
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
    """Render `edges` ({from, component, action, to}) as a Mermaid flowchart."""
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
    """Reads `site`'s crawl graph and produces the final PRD markdown.
    Details: docs/dev/generators/graph_prd_synthesizer.md#graphprdsynthesizer
    """

    def __init__(self, agent: Agent, graph_store: GraphStore, batch_size: int = 5) -> None:
        self.agent = agent
        self.graph_store = graph_store
        # Pages per batch-summarize call; deliberately small - see doc.
        # Details: docs/dev/generators/graph_prd_synthesizer.md#batch_size
        self.batch_size = batch_size

    def _narrate_page_catalog(self, site: str) -> Dict[str, str]:
        """One `agent.generate()` call per page; a failure degrades to raw facts.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_narrate_page_catalog
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
        """One text block per page: route/status/count, description, catalog."""
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
        """Group into `batch_size` chunks, one bounded call per chunk.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_summarize_batches
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
        """Combine condensed section summaries into the overview narrative.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_reduce
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
        """Produce the final PRD markdown for `site` - the only method callers need.
        Details: docs/dev/generators/graph_prd_synthesizer.md#synthesize
        """
        rows = self.graph_store.get_progress_table_rows(site)
        edges = self.graph_store.get_edges(site)
        descriptions = self.graph_store.get_page_descriptions(site)
        catalog = self._narrate_page_catalog(site)

        page_lines = self._build_page_lines(rows, descriptions, catalog)
        section_summaries = self._summarize_batches(site, page_lines)
        overview = self._reduce(site, section_summaries)

        # Rendered deterministically, never asked of the model - see module doc.
        mermaid = build_mermaid_graph(edges)
        return f"{overview}\n\n## Navigation Graph\n\n{mermaid}\n"
