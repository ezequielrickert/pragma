"""Phase 5 of the crawl4ai migration: a deterministic ASCII/Unicode
component-tree document, separate from `GraphPRDSynthesizer`'s prose
"Digital Blueprint" - written to its own output file, never merged into or
replacing it.

First level: every crawled page, labeled by its own `<title>` (Phase 2).
Second level: every component discovered on that page (Phase 0's ghost-node
fix is what makes this level trustworthy at all) plus every static text block
(Phase 4) as a distinct leaf kind - never nested further, so a redirect target
is rendered as a reference back to its own first-level entry, not an inlined
subtree (the flat "first level: endpoints, second level: components" shape
this whole feature was asked for specifically avoids the graph-vs-tree cycle
a literal nested rendering would hit).

The tree *structure* is built and rendered entirely deterministically -
`build_component_tree`/`render_ascii_tree` never call an LLM. This was an
explicit, deliberate choice (not merely "simpler"): an LLM asked to
reproduce structured data as precisely-formatted text risks silently
smoothing over or fabricating exactly the kind of gap the ghost-node bug
(Phase 0) already showed can hide in this data undetected. AI narration
stays optional and out of this module entirely - if ever added, it must get
its own dedicated system_instruction, never shared with
`CATALOG_SYSTEM_INSTRUCTION`/`SYNTHESIS_SYSTEM_INSTRUCTION`, per
wiki/prompt-engineering-for-llm-agents.md Principle 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.interfaces import GraphStore
from .component_classifier import describe_options


@dataclass
class TreeLeaf:
    kind: str  # "component" | "text"
    path: str
    label: str
    text: str
    variants: List[str] = field(default_factory=list)
    placeholder_value: Optional[str] = None
    requests: List[str] = field(default_factory=list)
    redirect_target: Optional[str] = None


@dataclass
class TreePage:
    url: str
    title: str
    leaves: List[TreeLeaf] = field(default_factory=list)


@dataclass
class SiteTree:
    site: str
    pages: List[TreePage] = field(default_factory=list)


def _format_variants(parsed: Optional[Dict[str, Any]]) -> List[str]:
    """Render `describe_options`' normalized shape as short display strings -
    reuses the same three-shape disambiguation `graph_prd_synthesizer.py`'s
    catalog narration already relies on, so both consumers interpret the raw
    `options` JSON blob identically."""
    if not parsed:
        return []
    if parsed["kind"] == "stepper":
        current_value = parsed.get("current_value")
        return [f"stepper (current value: {current_value})" if current_value else "stepper"]
    if parsed["kind"] in ("choice_group", "revealed_options"):
        out = []
        for choice in parsed["choices"]:
            text = choice.get("text")
            if not text:
                continue
            out.append(f"{text} (selected)" if choice.get("selected") else text)
        return out
    return []


def _render_request_line(request: Dict[str, Any]) -> str:
    if request.get("failed"):
        outcome = f"FAILED ({request.get('failure_text') or 'unknown error'})"
    elif request.get("status") is not None:
        outcome = str(request["status"])
    else:
        outcome = "? (no response captured)"
    return f"{request.get('method', '')} {request.get('url', '')} -> {outcome}"


def build_component_tree(graph_store: GraphStore, site: str) -> SiteTree:
    """Pure, deterministic read of `GraphStore` into an in-memory tree
    structure - no rendering, no AI. Kept separate from `render_ascii_tree`
    so the *structure* is independently unit-testable (assert on `TreeLeaf`
    field values) without coupling tests to exact box-drawing characters.
    """
    rows = graph_store.get_progress_table_rows(site)
    titles = graph_store.get_page_titles(site)
    ledger = graph_store.get_component_ledger(site)
    text_ledger = graph_store.get_text_content_ledger(site)
    edges = graph_store.get_edges(site)

    # Fallback/cross-check only - a component's own last interaction's
    # resulting_url (below) is the primary redirect-target source, since
    # it's already local to the ledger entry. mechanical_loop.py calls
    # sink.record_interaction(...) and sink.record_navigation_edge(...)
    # back-to-back from the identical `new_key` for any navigating
    # interaction, so the two must never disagree by construction - a real
    # disagreement would itself be a persistence bug to investigate, not a
    # data-quality gap to paper over silently.
    redirect_index: Dict[Tuple[str, str], str] = {(e["from"], e["component"]): e["to"] for e in edges}

    pages: List[TreePage] = []
    for row in sorted(rows, key=lambda r: r["url"]):
        url = row["url"]
        title = titles.get(url) or url
        leaves: List[TreeLeaf] = []

        for path in sorted(ledger.get(url, {}).keys()):
            record = ledger[url][path]
            parsed = describe_options(record.get("options") or "")

            placeholder_value = None
            redirect_target_url = None
            for interaction in record.get("interactions", []):
                if interaction.get("action") == "fill" and interaction.get("value"):
                    placeholder_value = interaction["value"]
                if interaction.get("resulting_url"):
                    redirect_target_url = interaction["resulting_url"]
            if not redirect_target_url:
                redirect_target_url = redirect_index.get((url, path))

            redirect_label = None
            if redirect_target_url:
                target_title = titles.get(redirect_target_url) or redirect_target_url
                redirect_label = f'"{target_title}" ({redirect_target_url})'

            leaves.append(
                TreeLeaf(
                    kind="component",
                    path=path,
                    label=record.get("component_type") or record.get("tag") or "element",
                    text=record.get("text") or "",
                    variants=_format_variants(parsed),
                    placeholder_value=placeholder_value,
                    requests=[_render_request_line(r) for r in record.get("network_requests", [])],
                    redirect_target=redirect_label,
                )
            )

        for entry in sorted(text_ledger.get(url, []), key=lambda e: e.get("path", "")):
            leaves.append(
                TreeLeaf(
                    kind="text",
                    path=entry.get("path", ""),
                    label=entry.get("tag") or "text",
                    text=entry.get("text") or "",
                )
            )

        pages.append(TreePage(url=url, title=title, leaves=leaves))

    return SiteTree(site=site, pages=pages)


def _render_leaf_line(leaf: TreeLeaf) -> str:
    if leaf.kind == "text":
        return f"[text: {leaf.label}] {leaf.text}"
    parts = [f"[{leaf.label}]"]
    if leaf.text:
        parts.append(f'"{leaf.text}"')
    if leaf.variants:
        parts.append("variants=[" + ", ".join(leaf.variants) + "]")
    if leaf.placeholder_value:
        parts.append(f"placeholder={leaf.placeholder_value!r}")
    if leaf.requests:
        parts.append("requests=[" + "; ".join(leaf.requests) + "]")
    if leaf.redirect_target:
        parts.append(f"-> {leaf.redirect_target}")
    return " ".join(parts)


def render_ascii_tree(tree: SiteTree, use_box_drawing: bool = True) -> str:
    """Deterministic string rendering of an already-built `SiteTree` - no
    `GraphStore`/AI access at all. Two calls against identical input produce
    byte-identical output regardless of anything else happening in the
    process - this is what "rendered deterministically by code, not by an
    LLM" cashes out to concretely.
    """
    if use_box_drawing:
        branch, last_branch, pipe, space = "├── ", "└── ", "│   ", "    "
    else:
        branch, last_branch, pipe, space = "|-- ", "`-- ", "|   ", "    "

    lines = [f"{tree.site}/"]
    for i, page in enumerate(tree.pages):
        page_is_last = i == len(tree.pages) - 1
        lines.append(f"{last_branch if page_is_last else branch}{page.title} ({page.url})")
        child_indent = space if page_is_last else pipe

        for j, leaf in enumerate(page.leaves):
            leaf_is_last = j == len(page.leaves) - 1
            leaf_prefix = last_branch if leaf_is_last else branch
            lines.append(f"{child_indent}{leaf_prefix}{_render_leaf_line(leaf)}")

    return "\n".join(lines) + "\n"


def generate_component_tree_document(graph_store: GraphStore, site: str, use_box_drawing: bool = True) -> str:
    """Top-level entry point `Engine` calls: `build_component_tree()` +
    `render_ascii_tree()`, composed, plus a short header - mirrors
    `GraphPRDSynthesizer.synthesize()`'s own "one function, no further
    ceremony" shape.
    """
    tree = build_component_tree(graph_store, site)
    component_count = sum(1 for p in tree.pages for leaf in p.leaves if leaf.kind == "component")
    text_count = sum(1 for p in tree.pages for leaf in p.leaves if leaf.kind == "text")

    header = (
        f"# Component Tree: {site}\n\n"
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"{len(tree.pages)} pages, {component_count} components, {text_count} text blocks\n\n"
        "```\n"
    )
    return header + render_ascii_tree(tree, use_box_drawing=use_box_drawing) + "```\n"
