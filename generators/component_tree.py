"""A deterministic ASCII/Unicode component-tree document, its own output file.
Details: docs/dev/generators/component_tree.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from .component_classifier import choice_text_by_path, describe_options_from_rows, format_option_choices


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
    # One line per consolidated choice-group member that triggered its own
    # distinct outcome - see _build_option_redirects. Empty for every leaf
    # that isn't a consolidated dropdown/choice group.
    option_redirects: List[str] = field(default_factory=list)
    # The landmark region this leaf sits in ("navigation", "main", ...), or
    # "" when it is in none - which is also what every leaf reports for a
    # crawl recorded before structural containment capture existed.
    # Details: docs/dev/generators/component_tree.md#region
    region: str = ""


@dataclass
class TreePage:
    url: str
    title: str
    leaves: List[TreeLeaf] = field(default_factory=list)


@dataclass
class SiteTree:
    site: str
    pages: List[TreePage] = field(default_factory=list)


def _build_option_redirects(
    record: Dict[str, Any], parsed: Optional[Dict[str, Any]], titles: Dict[str, str]
) -> List[str]:
    """One line per consolidated choice-group member that actually triggered
    its own outcome - the fact a per-option Component node used to carry on
    its own now lives here instead, on the group's single node, tagged with
    which specific option (`source_path`, see GraphStoreSink._resolve_write_path)
    caused it. Details: docs/dev/generators/component_tree.md#_build_option_redirects
    """
    if not parsed or parsed["kind"] != "choice_group":
        return []
    text_by_path = choice_text_by_path(parsed)

    lines = []
    for interaction in record.get("interactions", []):
        source_path = interaction.get("source_path")
        if not source_path:
            continue
        label = text_by_path.get(source_path) or source_path
        resulting_url = interaction.get("resulting_url")
        if resulting_url:
            target_title = titles.get(resulting_url) or resulting_url
            lines.append(f'"{label}" -> "{target_title}" ({resulting_url})')
        else:
            lines.append(f'"{label}" ({interaction.get("action", "")})')
    return lines


def _render_request_line(request: Dict[str, Any]) -> str:
    if request.get("failed"):
        outcome = f"FAILED ({request.get('failure_text') or 'unknown error'})"
    elif request.get("status") is not None:
        outcome = str(request["status"])
    else:
        outcome = "? (no response captured)"
    return f"{request.get('method', '')} {request.get('path', '')} -> {outcome}"


def build_component_tree(graph_store: Any, site: str) -> SiteTree:
    """Pure, deterministic read of the graph store into an in-memory tree
    structure. `site` labels the tree's own root (`SiteTree.site`,
    rendered as the ASCII tree's top line) - the store itself needs no
    `site` argument, already scoped to exactly one by construction.
    Details: docs/dev/generators/component_tree.md#build_component_tree
    """
    rows = graph_store.get_progress_table_rows()
    titles = graph_store.get_page_titles()
    ledger = graph_store.get_component_ledger()
    text_ledger = graph_store.get_text_content_ledger()
    edges = graph_store.get_edges()
    # Which landmark region each component sits in. Text leaves get no
    # region: containment is recorded per interactive component, and
    # inventing one for a text node by proximity would be a guess.
    # Details: docs/dev/generators/component_tree.md#regions
    regions = graph_store.get_component_regions()

    # Fallback/cross-check only - a component's own resulting_url is primary.
    # Details: docs/dev/generators/component_tree.md#redirect_index
    redirect_index: Dict[Tuple[str, str], str] = {(e["from"], e["component"]): e["to"] for e in edges}

    pages: List[TreePage] = []
    for row in sorted(rows, key=lambda r: r["url"]):
        url = row["url"]
        title = titles.get(url) or url
        leaves: List[TreeLeaf] = []

        for path in sorted(ledger.get(url, {}).keys()):
            record = ledger[url][path]
            parsed = describe_options_from_rows(*record.get("options", ([], "")))

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
                    variants=format_option_choices(parsed),
                    placeholder_value=placeholder_value,
                    requests=[_render_request_line(r) for r in record.get("network_requests", [])],
                    redirect_target=redirect_label,
                    option_redirects=_build_option_redirects(record, parsed, titles),
                    region=regions.get(url, {}).get(path, ""),
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


def group_by_region(leaves: List[TreeLeaf]) -> List[Tuple[str, List[TreeLeaf]]]:
    """A page's leaves as `[(landmark, leaves)]`, landmarks first.

    The hierarchy lives here rather than on `TreePage` on purpose: a leaf
    knowing its own region is a fact about the leaf, while nesting is a way
    of showing it. Keeping the built tree flat means `build_component_tree`
    stays a straight read of the store and every caller that just wants
    "every leaf on this page" still gets it without walking two levels.

    Leaves in no landmark region come last under `""`, so a page whose
    containment was never recorded renders exactly as it did before this
    grouping existed - one flat list, no empty region headers.
    Details: docs/dev/generators/component_tree.md#group_by_region
    """
    by_region: Dict[str, List[TreeLeaf]] = {}
    for leaf in leaves:
        by_region.setdefault(leaf.region, []).append(leaf)
    named = sorted((region, group) for region, group in by_region.items() if region)
    unnamed = [("", by_region[""])] if "" in by_region else []
    return named + unnamed


def render_ascii_tree(tree: SiteTree, use_box_drawing: bool = True) -> str:
    """Deterministic string rendering of an already-built `SiteTree`; no AI access.
    Details: docs/dev/generators/component_tree.md#render_ascii_tree
    """
    if use_box_drawing:
        branch, last_branch, pipe, space = "├── ", "└── ", "│   ", "    "
    else:
        branch, last_branch, pipe, space = "|-- ", "`-- ", "|   ", "    "

    def render_leaves(leaves: List[TreeLeaf], indent: str) -> None:
        for position, leaf in enumerate(leaves):
            is_last = position == len(leaves) - 1
            lines.append(f"{indent}{last_branch if is_last else branch}{_render_leaf_line(leaf)}")
            redirect_indent = indent + (space if is_last else pipe)
            for redirect_position, redirect_line in enumerate(leaf.option_redirects):
                redirect_is_last = redirect_position == len(leaf.option_redirects) - 1
                lines.append(
                    f"{redirect_indent}{last_branch if redirect_is_last else branch}{redirect_line}"
                )

    lines = [f"{tree.site}/"]
    for i, page in enumerate(tree.pages):
        page_is_last = i == len(tree.pages) - 1
        lines.append(f"{last_branch if page_is_last else branch}{page.title} ({page.url})")
        child_indent = space if page_is_last else pipe

        groups = group_by_region(page.leaves)
        # A page with nothing in a landmark keeps its leaves directly under
        # it: a single "(no region)" header above every leaf on the page
        # would be one more level of indentation carrying no information.
        if len(groups) == 1 and not groups[0][0]:
            render_leaves(page.leaves, child_indent)
            continue

        for group_position, (landmark, group) in enumerate(groups):
            group_is_last = group_position == len(groups) - 1
            header = f"<{landmark}>" if landmark else "(no landmark region)"
            lines.append(f"{child_indent}{last_branch if group_is_last else branch}{header}")
            render_leaves(group, child_indent + (space if group_is_last else pipe))

    return "\n".join(lines) + "\n"


def generate_component_tree_document(graph_store: Any, site: str, use_box_drawing: bool = True) -> str:
    """Top-level entry point `Engine` calls: build + render + a short header.
    Details: docs/dev/generators/component_tree.md#generate_component_tree_document
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


@DOCUMENT_REGISTRY.register("tree")
class ComponentTreeDocument(DocumentGenerator):
    """Pipeline adapter for `generate_component_tree_document`.
    Details: docs/dev/generators/component_tree.md#componenttreedocument
    """

    name = "tree"
    title = "Component Tree"
    purpose = "Every page's controls and text, as a nested tree - the fastest way to read one screen."

    def generate(self, request: DocumentRequest) -> str:
        use_box_drawing = not request.settings.get("tree_ascii", False)
        return generate_component_tree_document(request.graph_store, request.site, use_box_drawing=use_box_drawing)
