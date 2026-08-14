"""How much of the site a crawl actually reached - the number that bounds
how complete every other document can be.

Why this is its own document *and* a banner on all the others: every
generator here describes what the crawl found, and none of them can
describe what it never reached. An OpenAPI contract built from a crawl
that covered 40% of an application looks exactly like one built from full
coverage. Stating the fraction on the document itself is the difference
between an honest artifact and a misleading one.

Details: docs/dev/generators/coverage.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.documents import DocumentGenerator, DocumentRequest
from core.interfaces import GraphStore
from core.registry import DOCUMENT_REGISTRY

# Stated on every document, not just this one. The crawl has no login
# (see research/plan-generacion-de-documentos.md H3), so "100% of pages"
# means 100% of what is reachable without signing in.
# Details: docs/dev/generators/coverage.md#public_surface_caveat
PUBLIC_SURFACE_CAVEAT = (
    "Scope: the site's public surface. The crawl does not sign in, so any page or flow behind "
    "authentication is absent from this document and is not counted as missing below."
)


@dataclass(frozen=True)
class CrawlCoverage:
    """One crawl's reach, in the four numbers that bound every document.
    Details: docs/dev/generators/coverage.md#crawlcoverage
    """

    pages_finished: int
    pages_total: int
    components_explored: int
    components_total: int
    endpoints_discovered: int
    unfinished_urls: List[str]

    @property
    def pages_percent(self) -> int:
        return _percent(self.pages_finished, self.pages_total)

    @property
    def components_percent(self) -> int:
        return _percent(self.components_explored, self.components_total)


def _percent(part: int, whole: int) -> int:
    """Whole-number percentage, with an empty crawl reported as 0% rather
    than crashing - a site with nothing recorded is a real (if useless)
    outcome, not an error the caller should have to guard against."""
    return round(100 * part / whole) if whole else 0


def build_coverage(graph_store: GraphStore, site: str) -> CrawlCoverage:
    """Read `site`'s reach from the store. Pure read, no LLM, no writes.
    Details: docs/dev/generators/coverage.md#build_coverage
    """
    pages_finished, pages_total = graph_store.count_visited(site)
    components_unexplored, components_total = graph_store.count_unexplored_components(site)
    unfinished = [
        row["url"] for row in graph_store.get_progress_table_rows(site) if row.get("status") != "Finished"
    ]
    return CrawlCoverage(
        pages_finished=pages_finished,
        pages_total=pages_total,
        components_explored=components_total - components_unexplored,
        components_total=components_total,
        endpoints_discovered=len(graph_store.get_inferred_requests(site)),
        unfinished_urls=sorted(unfinished),
    )


def render_coverage_banner(coverage: CrawlCoverage, stopped_reason: str = "") -> str:
    """The block every Markdown document opens with.

    `stopped_reason` names the budget that cut the run short, when one did.
    Without it a partial document is indistinguishable from a complete one
    for a small site: "3/40 pages" reads the same whether the crawl found
    only three pages or was told to stop after three. The difference matters
    because one of them is finished and the other has a next run.
    Details: docs/dev/generators/coverage.md#render_coverage_banner
    """
    partial = (
        f">\n> **This run stopped early:** {stopped_reason}. The pages it did not reach are "
        f"still recorded as pending - run the same URL again to continue from there.\n"
        if stopped_reason
        else ""
    )
    return (
        f"> **Crawl coverage:** {coverage.pages_finished}/{coverage.pages_total} pages "
        f"({coverage.pages_percent}%), {coverage.components_explored}/{coverage.components_total} "
        f"components interacted with ({coverage.components_percent}%), "
        f"{coverage.endpoints_discovered} API endpoints discovered.\n"
        f"{partial}"
        f">\n"
        f"> {PUBLIC_SURFACE_CAVEAT}\n"
    )


@DOCUMENT_REGISTRY.register("coverage")
class CoverageDocument(DocumentGenerator):
    """D9: the coverage report as a document of its own.
    Details: docs/dev/generators/coverage.md#coveragedocument
    """

    name = "coverage"
    title = "Crawl Coverage"
    purpose = "How much of the application this run actually reached - the ceiling on every other document."

    def generate(self, request: DocumentRequest) -> str:
        coverage = build_coverage(request.graph_store, request.site)
        lines = [
            f"# Crawl Coverage: {request.site}",
            "",
            PUBLIC_SURFACE_CAVEAT,
            "",
            "| Measure | Reached | Total | Coverage |",
            "|---|---|---|---|",
            f"| Pages visited | {coverage.pages_finished} | {coverage.pages_total} | {coverage.pages_percent}% |",
            f"| Components interacted with | {coverage.components_explored} | {coverage.components_total} "
            f"| {coverage.components_percent}% |",
            f"| API endpoints discovered | {coverage.endpoints_discovered} | - | - |",
            "",
        ]
        if coverage.unfinished_urls:
            lines.append("## Pages left unfinished")
            lines.append("")
            lines.append(
                "These were discovered but never completed a full interaction pass. Anything they "
                "contain is missing from every other document in this run."
            )
            lines.append("")
            lines.extend(f"- {url}" for url in coverage.unfinished_urls)
            lines.append("")
        return "\n".join(lines)
