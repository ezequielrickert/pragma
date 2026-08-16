"""Post-hoc PRD synthesis from `GraphStore`: map, batch-summarize, reduce.
Details: docs/dev/generators/graph_prd_synthesizer.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.interfaces import Agent, GraphStore
from core.registry import DOCUMENT_REGISTRY
from .component_classifier import choice_text_by_path, describe_options

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

# Combine stage: same shape as the reduce call below, but its output feeds
# back into another reduce rather than being the final overview - used only
# when there are more sections than one reduce call should take at once.
# Details: docs/dev/generators/graph_prd_synthesizer.md#combine_system_instruction
COMBINE_SYSTEM_INSTRUCTION = (
    "You are combining several already-condensed section summaries of a web application's Digital "
    "Blueprint into one shorter combined summary covering all of them, for a later step to combine "
    "further. Preserve every distinct fact and section name; do not add an overall narrative framing "
    "yet - that happens in a later step. Do not invent pages, routes, or components not present in the "
    "provided summaries."
)

# A real page can carry 100-300+ raw components before choice-group/stepper
# consolidation; a page's own narration prompt has no other bound on how
# many go in. Cap deterministically (facts are already sorted by path) and
# say so in the rendered block, rather than silently dropping the rest -
# the same "bounded, not exhaustive" discipline axe_run.js's per-rule node
# cap and probe_focus.js's _MAX_TAB_STEPS already apply elsewhere in this
# pipeline. wiki/local-and-small-model-constraints.md's own checklist named
# this exact surface: a max_tokens truncation already cost 4/4 runs their
# documents before the map/reduce split existed - this is the map stage's
# remaining unbounded input.
_MAX_FACTS_PER_PAGE = 60

# Reduce-stage input is the number of *sections* (batch_size pages each),
# not pages - a 200-page site at the default batch_size=5 still produces 40
# sections, which the old single reduce() call joined unconditionally into
# one prompt. Chunk-and-recurse (_reduce below) once past this many, rather
# than growing the very call this map-reduce split exists to bound.
_MAX_SECTIONS_PER_REDUCE = 8


def _choices_leading_elsewhere(record: Dict[str, Any], parsed: Dict[str, Any]) -> List[str]:
    """`"choice text -> resulting_url"` for every consolidated choice-group
    member whose own interaction navigated somewhere - a single node now
    covers the whole group, but a specific choice behaving differently from
    its siblings is still a fact worth narrating, not one that disappeared
    along with its old dedicated node.
    Details: docs/dev/generators/graph_prd_synthesizer.md#_choices_leading_elsewhere
    """
    text_by_path = choice_text_by_path(parsed)
    return [
        f"{text_by_path.get(interaction['source_path'], interaction['source_path'])} -> {interaction['resulting_url']}"
        for interaction in record.get("interactions", [])
        if interaction.get("source_path") and interaction.get("resulting_url")
    ]


def _build_page_facts(page_components: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """One catalog-ready fact dict per distinct control on a page, capped
    at `_MAX_FACTS_PER_PAGE` - see that constant's own comment.

    Returns:
        `(facts, truncated)` - `truncated` is `True` only when the cap
        itself is what stopped the loop, distinct from a page whose own
        component count is simply small (or reduced further by
        stepper/choice-group consolidation, which is unrelated to the
        cap) - `len(facts) < len(page_components)` alone can't tell those
        two cases apart.
    Details: docs/dev/generators/graph_prd_synthesizer.md#_build_page_facts
    """
    facts: List[Dict[str, Any]] = []
    seen_stepper_containers = set()
    seen_choice_groups = set()
    truncated = False
    for path in sorted(page_components.keys()):
        if len(facts) >= _MAX_FACTS_PER_PAGE:
            truncated = True
            break
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
            fact = {
                "type": "choice group (dropdown/menu/radio/checkbox)",
                "text": f"group '{group}'",
                "choices": [c["text"] for c in parsed["choices"] if c.get("text")],
                "interacted": bool(record.get("interacted")),
            }
            leads_elsewhere = _choices_leading_elsewhere(record, parsed)
            if leads_elsewhere:
                fact["leads_elsewhere"] = leads_elsewhere
            facts.append(fact)
            continue

        text = record.get("text") or "(no accessible label found on this element)"
        facts.append(
            {
                "type": record.get("component_type") or "element",
                "text": text,
                "interacted": bool(record.get("interacted")),
            }
        )
    return facts, truncated


def _render_fact_line(index: int, fact: Dict[str, Any]) -> str:
    parts = [f"type={fact['type']!r}", f"text={fact.get('text', '')!r}", f"interacted={fact.get('interacted')}"]
    if "current_value" in fact:
        parts.append(f"current_value={fact['current_value']!r}")
    if "choices" in fact:
        parts.append(f"choices={fact['choices']!r}")
    if "leads_elsewhere" in fact:
        parts.append(f"leads_elsewhere={fact['leads_elsewhere']!r}")
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

        Prints a `page i/n` line per call - see
        research/plan-progreso-en-terminal.md for why this loop and
        `narrate_family_purposes` are the two that needed a counter.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_narrate_page_catalog
        """
        ledger = self.graph_store.get_component_ledger(site)
        narrations: Dict[str, str] = {}
        # Pages whose facts come back empty are skipped without a call, so
        # like the family narrator the denominator counts calls, not pages.
        facts_by_page = {}
        truncated_pages = set()
        for page_url in sorted(ledger.keys()):
            facts, truncated = _build_page_facts(ledger[page_url])
            if facts:
                facts_by_page[page_url] = facts
            if truncated:
                truncated_pages.add(page_url)
        if facts_by_page:
            print(f"Narrating {len(facts_by_page)} page catalogs ({len(facts_by_page)} model calls)...")
        if truncated_pages:
            print(f"  {len(truncated_pages)} page(s) exceeded {_MAX_FACTS_PER_PAGE} components; showing the first {_MAX_FACTS_PER_PAGE}.")
        for page_number, (page_url, facts) in enumerate(facts_by_page.items(), 1):
            facts_block = "\n".join(_render_fact_line(i, f) for i, f in enumerate(facts, 1))
            if page_url in truncated_pages:
                facts_block += f"\n... and more components not shown (capped at {_MAX_FACTS_PER_PAGE})."
            print(f"  page {page_number}/{len(facts_by_page)}: {page_url}")
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
        if batches:
            print(f"Summarizing {len(batches)} sections ({len(batches)} model calls)...")
        summaries: List[str] = []
        for batch_number, batch in enumerate(batches, 1):
            print(f"  section {batch_number}/{len(batches)} ({len(batch)} pages)")
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

    @staticmethod
    def _section_summaries_prompt(site: str, section_summaries: List[str], closing_instruction: str) -> str:
        """Shared by `_combine_chunk` and `_reduce`'s terminal call - same
        "site + numbered section summaries" framing either way, differing
        only in what the model is asked to produce from them.
        """
        return (
            f"Site: {site}\n\n"
            f"Section summaries ({len(section_summaries)}):\n\n" + "\n\n---\n\n".join(section_summaries) + "\n\n"
            + closing_instruction
        )

    def _combine_chunk(self, site: str, chunk: List[str], chunk_number: int, total_chunks: int) -> str:
        """One intermediate combine call: fewer, larger summaries, never
        the final overview itself - see `COMBINE_SYSTEM_INSTRUCTION`.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_combine_chunk
        """
        print(f"  combining chunk {chunk_number}/{total_chunks} ({len(chunk)} sections)...")
        prompt = self._section_summaries_prompt(site, chunk, "Write the combined summary.")
        try:
            return self.agent.generate(prompt, system_instruction=COMBINE_SYSTEM_INSTRUCTION)
        except Exception as exc:  # noqa: BLE001 - degrade to raw sections, don't abort the run
            return f"_(chunk combine unavailable: {exc})_\n\n" + "\n\n".join(chunk)

    def _reduce(self, site: str, section_summaries: List[str]) -> str:
        """Combine condensed section summaries into the overview narrative.

        Chunked and recursively combined first when there are more than
        `_MAX_SECTIONS_PER_REDUCE` of them, so the final reduce call's own
        prompt never grows past the same bound this whole map-reduce split
        exists to enforce - a 200-page site at the default batch_size=5
        produces 40 sections, which the un-chunked version joined
        unconditionally into one prompt. Recursion terminates because each
        chunk collapses `_MAX_SECTIONS_PER_REDUCE` summaries into one
        combined summary, so the list strictly shrinks every call.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_reduce
        """
        if len(section_summaries) > _MAX_SECTIONS_PER_REDUCE:
            chunks = [
                section_summaries[i : i + _MAX_SECTIONS_PER_REDUCE]
                for i in range(0, len(section_summaries), _MAX_SECTIONS_PER_REDUCE)
            ]
            print(
                f"Reduce stage: {len(section_summaries)} sections exceed "
                f"{_MAX_SECTIONS_PER_REDUCE} per call; combining into {len(chunks)} chunk(s) first..."
            )
            combined = [self._combine_chunk(site, chunk, i, len(chunks)) for i, chunk in enumerate(chunks, 1)]
            return self._reduce(site, combined)

        print(f"Reducing {len(section_summaries)} section summaries into the overview (1 model call)...")
        prompt = self._section_summaries_prompt(site, section_summaries, "Write the overview narrative.")
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


@DOCUMENT_REGISTRY.register("prd")
class PRDDocument(DocumentGenerator):
    """Pipeline adapter for `GraphPRDSynthesizer`.
    Details: docs/dev/generators/graph_prd_synthesizer.md#prddocument
    """

    name = "prd"
    title = "Digital Blueprint"
    purpose = "Narrative walkthrough of what the application does, page by page, plus its navigation graph."

    def generate(self, request: DocumentRequest) -> str:
        batch_size = request.settings.get("prd_synth_batch_size", 5)
        synthesizer = GraphPRDSynthesizer(request.agent, request.graph_store, batch_size=batch_size)
        return synthesizer.synthesize(request.site)
