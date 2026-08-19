"""D13: how many parts this application has, how deep it goes, where it
narrows, and who else it talks to.

Everything here was already being computed or captured and had no reader.
`Engine`'s projection pass writes module, click depth, centrality and
articulation points onto every `Page` each run; the crawl records every
third-party endpoint it saw. No document showed any of it, so the one
question a modernisation asks first - "what is this thing made of" - had no
answer in the output.

Fully deterministic, no model call. A module's name is
`graph_projection._module_label`'s shared-URL-prefix label; naming it better
would be a separate, explicitly-impure step, the same split
`component_family_narrator.py` draws.

Details: docs/dev/generators/architecture_map.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from analysis.graph_projection import module_display_name
from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY

# Third-party hosts listed individually before the rest are summed into one
# "other" row. A real application talks to a long tail of analytics and font
# CDNs; a table with sixty rows of them buries the three that matter.
# Details: docs/dev/generators/architecture_map.md#_max_hosts_listed
_MAX_HOSTS_LISTED = 15


@dataclass(frozen=True)
class ModuleSummary:
    """One module's shape.
    Details: docs/dev/generators/architecture_map.md#modulesummary
    """

    label: str
    page_count: int
    entry_page: str
    # None when no page in the module is reachable from the entry point.
    shallowest_depth: Optional[int]
    deepest_depth: Optional[int]
    articulation_points: Tuple[str, ...]


def _depths(pages: Sequence[Dict[str, Any]]) -> List[int]:
    return sorted(p["click_depth"] for p in pages if p.get("click_depth") is not None)


def summarize_modules(metrics: Sequence[Dict[str, Any]]) -> List[ModuleSummary]:
    """One `ModuleSummary` per module, largest first.

    A page with no module is left out entirely rather than pooled into a
    synthetic module: this document's module table answers "what parts does
    the application have", and a page that belongs to no part is not a part.
    The depth table below still counts it, so it is reported, just not as
    something it is not.
    Details: docs/dev/generators/architecture_map.md#summarize_modules
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for page in metrics:
        if page.get("module_id") is None:
            continue
        label = module_display_name(page["module_id"], page.get("module_label", ""))
        grouped.setdefault(label, []).append(page)

    summaries = []
    for label, pages in grouped.items():
        depths = _depths(pages)
        # The shallowest page is the module's front door. Ties break by url
        # so the choice is stable across runs.
        entry = min(
            pages,
            key=lambda p: (p["click_depth"] is None, p.get("click_depth") or 0, p["url"]),
        )
        summaries.append(
            ModuleSummary(
                label=label,
                page_count=len(pages),
                entry_page=entry["url"],
                shallowest_depth=depths[0] if depths else None,
                deepest_depth=depths[-1] if depths else None,
                articulation_points=tuple(
                    sorted(p["url"] for p in pages if p.get("is_articulation_point"))
                ),
            )
        )
    return sorted(summaries, key=lambda s: (-s.page_count, s.label))


def hosts_by_traffic(integrations: Sequence[Dict[str, Any]]) -> List[Tuple[str, int, int]]:
    """`[(host, calls, endpoint_count)]`, busiest first.

    `integrations()` returns one row per third-party endpoint; a reader wants
    one row per third party. Which services this application depends on is
    the question, and it is asked per vendor, not per URL.
    Details: docs/dev/generators/architecture_map.md#hosts_by_traffic
    """
    totals: Dict[str, List[int]] = {}
    for endpoint in integrations:
        entry = totals.setdefault(endpoint.get("host") or "(unknown host)", [0, 0])
        entry[0] += endpoint.get("call_count") or 0
        entry[1] += 1
    return sorted(
        ((host, calls, endpoints) for host, (calls, endpoints) in totals.items()),
        key=lambda row: (-row[1], -row[2], row[0]),
    )


def _module_table(summaries: Sequence[ModuleSummary]) -> List[str]:
    lines = [
        "## Modules",
        "",
        f"{len(summaries)} module(s), largest first. A module is a cluster of pages that link to "
        "each other more than to the rest of the site - the parts the application is actually "
        "built from, rather than the ones its navigation menu advertises.",
        "",
        "| Module | Pages | Front door | Depth |",
        "|---|---|---|---|",
    ]
    for summary in summaries:
        if summary.shallowest_depth is None:
            depth = "unreachable from the entry point"
        elif summary.shallowest_depth == summary.deepest_depth:
            depth = f"{summary.shallowest_depth}"
        else:
            depth = f"{summary.shallowest_depth}-{summary.deepest_depth}"
        lines.append(
            f"| {summary.label} | {summary.page_count} | {summary.entry_page} | {depth} |"
        )
    return lines + [""]


def _bottleneck_section(summaries: Sequence[ModuleSummary]) -> List[str]:
    bottlenecks = [
        (summary.label, url) for summary in summaries for url in summary.articulation_points
    ]
    if not bottlenecks:
        return [
            "## Bottlenecks",
            "",
            "No page is the only route to any other. Every part of the crawled surface can be "
            "reached more than one way.",
            "",
        ]
    return [
        "## Bottlenecks",
        "",
        f"{len(bottlenecks)} page(s) with no alternate route around them: removing one "
        "disconnects part of the site. In a rebuild these are where a broken link costs the "
        "most, and where a redirect has to keep working.",
        "",
        "| Page | Module |",
        "|---|---|",
    ] + [f"| {url} | {label} |" for label, url in sorted(bottlenecks)] + [""]


def _depth_section(metrics: Sequence[Dict[str, Any]]) -> List[str]:
    by_depth: Dict[int, int] = {}
    unreachable = 0
    for page in metrics:
        depth = page.get("click_depth")
        if depth is None:
            unreachable += 1
        else:
            by_depth[depth] = by_depth.get(depth, 0) + 1

    lines = [
        "## How deep it goes",
        "",
        "Pages by how many clicks from the entry point the crawl needed to reach them.",
        "",
        "| Clicks from entry | Pages |",
        "|---|---|",
    ]
    lines += [f"| {depth} | {count} |" for depth, count in sorted(by_depth.items())]
    if unreachable:
        lines += [
            "",
            f"{unreachable} page(s) were recorded but are not reachable from the entry point by "
            "any navigation the crawl observed. They were found as links, so something points at "
            "them - just not along a path this crawl walked.",
        ]
    return lines + [""]


def _integrations_section(integrations: Sequence[Dict[str, Any]]) -> List[str]:
    hosts = hosts_by_traffic(integrations)
    if not hosts:
        return [
            "## Third-party integrations",
            "",
            "No third-party HTTP traffic was observed. For a crawl that reached real pages this "
            "usually means the application genuinely calls only its own API.",
            "",
        ]
    listed, rest = hosts[:_MAX_HOSTS_LISTED], hosts[_MAX_HOSTS_LISTED:]
    lines = [
        "## Third-party integrations",
        "",
        f"{len(hosts)} host(s) this application calls but does not own, busiest first. Each is a "
        "dependency a rebuild either keeps, replaces, or drops on purpose.",
        "",
        "| Host | Calls observed | Distinct endpoints |",
        "|---|---|---|",
    ]
    lines += [f"| {host} | {calls} | {endpoints} |" for host, calls, endpoints in listed]
    if rest:
        lines.append(
            f"| _{len(rest)} further host(s)_ | {sum(r[1] for r in rest)} | {sum(r[2] for r in rest)} |"
        )
    return lines + [""]


@DOCUMENT_REGISTRY.register("architecture")
class ArchitectureMapDocument(DocumentGenerator):
    """Details: docs/dev/generators/architecture_map.md#architecturemapdocument"""

    name = "architecture"
    title = "Architecture Map"
    purpose = "The parts the application is built from, how deep they go, where it narrows, and who else it talks to."

    def generate(self, request: DocumentRequest) -> str:
        store = request.graph_store
        metrics = store.get_page_metrics()
        if not metrics:
            return (
                f"# Architecture Map: {request.site}\n\n"
                "No pages were recorded for this site, so there is no structure to describe.\n"
            )

        summaries = summarize_modules(metrics)
        lines = [f"# Architecture Map: {request.site}", ""]
        if not summaries:
            lines += [
                "No modules were detected. Either the projection pass never ran for this crawl, "
                "or the pages it found link to each other too sparsely to cluster - a crawl that "
                "stopped after a handful of pages usually looks like this.",
                "",
            ]
        else:
            lines += _module_table(summaries)
        lines += _bottleneck_section(summaries)
        lines += _depth_section(metrics)
        lines += _integrations_section(store.integrations())
        lines += [
            "## What this document does not show",
            "",
            "**Navigation cycles.** The projection pass enumerates them every run and nothing "
            "stores them - there is no column and no table - so they are absent here rather than "
            "recomputed. See `docs/dev/database/ladybug/analysis.md`.",
            "",
        ]
        return "\n".join(lines)
