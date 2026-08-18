"""Post-hoc PRD synthesis from the crawl graph: map, batch-summarize, reduce.
Details: docs/dev/generators/graph_prd_synthesizer.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.interfaces import Agent
from core.registry import DOCUMENT_REGISTRY
from .component_classifier import choice_text_by_path, describe_options_from_rows

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
        parsed = describe_options_from_rows(*record.get("options", ([], "")))

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


def _section_label(module_id: Optional[int], module_label: str) -> str:
    """What a module's section is called in the document.

    `module_label` is `graph_projection._module_label`'s deterministic
    shared-URL-prefix name, which is `""` for a module whose pages share no
    prefix - a real outcome, not a failure, so it falls back to the id
    rather than to an invented name. Pages the projection never assigned go
    last under their own heading: "not part of any module" is a fact about
    the site's shape, not a leftovers bucket to hide.
    Details: docs/dev/generators/graph_prd_synthesizer.md#_section_label
    """
    if module_id is None:
        return "Pages outside any module"
    return module_label or f"Module {module_id}"


def group_pages_by_module(
    rows: List[Dict[str, Any]], metrics: List[Dict[str, Any]]
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """`[(section label, rows)]` - the site's own structure, not batch order.

    Before this, sections were `batch_size`-sized slices of a url-sorted
    list: for a forty-page site the document's shape was decided by the
    chunk size, and two pages landed in the same section because they were
    alphabetically adjacent. Grouping by the Louvain module `Engine`'s
    projection pass already computed, and ordering each module's pages by
    click depth, means the document reads outside-in through parts that
    actually exist.

    Each returned row is a copy of its `get_progress_table_rows` row with
    `click_depth` and `is_articulation_point` merged in, so the prompt
    builder needs no second argument for them - joining metrics to pages is
    this function's job, and mutating the caller's rows is not.

    Sections are ordered by their label, unassigned pages last. Within a
    section, shallowest page first, `None` depth (unreachable from the root)
    last, then by url so the result is deterministic.
    Details: docs/dev/generators/graph_prd_synthesizer.md#group_pages_by_module
    """
    by_url = {m["url"]: m for m in metrics}
    sections: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for row in rows:
        metric = by_url.get(row["url"], {})
        label = _section_label(metric.get("module_id"), metric.get("module_label", ""))
        # Unassigned sorts after every named section regardless of label.
        key = (1 if metric.get("module_id") is None else 0, label)
        sections.setdefault(key, []).append({
            "click_depth": metric.get("click_depth"),
            "is_articulation_point": bool(metric.get("is_articulation_point")),
            **row,
        })

    def depth_then_url(row: Dict[str, Any]) -> Tuple[int, Any, str]:
        depth = row.get("click_depth")
        return (1, 0, row["url"]) if depth is None else (0, depth, row["url"])

    return [
        (label, sorted(section_rows, key=depth_then_url))
        for (_unassigned, label), section_rows in sorted(sections.items())
    ]


class GraphPRDSynthesizer:
    """Reads `site`'s crawl graph and produces the final PRD markdown.
    Details: docs/dev/generators/graph_prd_synthesizer.md#graphprdsynthesizer
    """

    def __init__(self, agent: Agent, graph_store: Any, batch_size: int = 5) -> None:
        self.agent = agent
        self.graph_store = graph_store
        # Pages per batch-summarize call; deliberately small - see doc.
        # Details: docs/dev/generators/graph_prd_synthesizer.md#batch_size
        self.batch_size = batch_size

    def _narrate_page_catalog(self) -> Dict[str, str]:
        """One `agent.generate()` call per page; a failure degrades to raw facts.

        Prints a `page i/n` line per call - see
        research/plan-progreso-en-terminal.md for why this loop and
        `narrate_family_purposes` are the two that needed a counter.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_narrate_page_catalog
        """
        ledger = self.graph_store.get_component_ledger()
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
        """One text block per page: route/status/count, structure, description, catalog.

        The structural facts come from the rows `group_pages_by_module`
        already merged them into. They are stated rather than left for the
        model to infer, because it cannot: "there is no alternate route
        around this page" is a property of the whole navigation graph, and a
        model handed one page at a time will either omit it or invent it.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_build_page_lines
        """
        page_lines = []
        for row in rows:
            url = row["url"]
            line = f"- {url} [{row['status']}, {row['components']} components]"
            if row.get("click_depth") is not None:
                line += f"\n  Reached in {row['click_depth']} click(s) from the entry point."
            if row.get("is_articulation_point"):
                line += (
                    "\n  Removing this page disconnects the navigation graph:"
                    " there is no alternate route around it."
                )
            if descriptions.get(url):
                line += f"\n  Description: {descriptions[url]}"
            if catalog.get(url):
                line += f"\n  Components:\n{catalog[url]}"
            page_lines.append(line)
        return page_lines

    def _summarize_sections(self, site: str, sections: List[Tuple[str, List[str]]]) -> List[str]:
        """One bounded call per section, named by the module it describes.

        `batch_size` still bounds a single prompt - a module with sixty
        pages cannot go in one call - so a large module becomes several
        calls carrying the same section name. What changed is that the chunk
        boundary no longer *defines* the section; it only splits one.
        Details: docs/dev/generators/graph_prd_synthesizer.md#_summarize_sections
        """
        chunks: List[Tuple[str, List[str]]] = [
            (label, lines[i : i + self.batch_size])
            for label, lines in sections
            for i in range(0, len(lines), self.batch_size)
        ]
        if chunks:
            print(f"Summarizing {len(sections)} module(s) in {len(chunks)} model calls...")
        summaries: List[str] = []
        for chunk_number, (label, chunk) in enumerate(chunks, 1):
            print(f"  section {chunk_number}/{len(chunks)}: {label} ({len(chunk)} pages)")
            chunk_block = "\n".join(chunk)
            prompt = (
                f"Site: {site}\n"
                f"Section: {label}\n\n"
                f"Pages in this section ({len(chunk)}):\n{chunk_block}\n\n"
                "Write the section summary."
            )
            try:
                summaries.append(self.agent.generate(prompt, system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION))
            except Exception as exc:  # noqa: BLE001 - degrade this one section, not the whole run
                summaries.append(f"_(section summary unavailable: {exc})_\n\n{chunk_block}")
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
        rows = self.graph_store.get_progress_table_rows()
        edges = self.graph_store.get_edges()
        descriptions = self.graph_store.get_page_descriptions()
        catalog = self._narrate_page_catalog()

        sections = [
            (label, self._build_page_lines(section_rows, descriptions, catalog))
            for label, section_rows in group_pages_by_module(
                rows, self.graph_store.get_page_metrics()
            )
        ]
        section_summaries = self._summarize_sections(site, sections)
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
