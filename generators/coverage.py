"""How much of the site a crawl actually reached - the number that bounds
how complete every other document can be.

Why this is its own document *and* a banner on all the others: every
generator here describes what the crawl found, and none of them can
describe what it never reached. An OpenAPI contract built from a crawl
that covered 40% of an application looks exactly like one built from full
coverage. Stating the fraction on the document itself is the difference
between an honest artifact and a misleading one.

`coverage.json` (docs/adr/0001) is the source of truth `coverage.md` and
every other document's banner render from - `CrawlCoverage` is computed
exactly once per run (`generators/pipeline.py::run_document_pipeline`),
never re-queried per document.

Details: docs/dev/generators/coverage.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema

# Stated on every document, not just this one. The crawl has no login
# (see research/plan-generacion-de-documentos.md H3), so "100% of pages"
# means 100% of what is reachable without signing in.
# Details: docs/dev/generators/coverage.md#public_surface_caveat
PUBLIC_SURFACE_CAVEAT = (
    "Scope: the site's public surface. The crawl does not sign in, so any page or flow behind "
    "authentication is absent from this document and is not counted as missing below."
)

_SCHEMA_PATH = "schemas/coverage.schema.json"


@dataclass(frozen=True)
class CrawlCoverage:
    """One crawl's reach, in the numbers that bound every document.
    Details: docs/dev/generators/coverage.md#crawlcoverage
    """

    pages_finished: int
    pages_total: int
    components_explored: int
    components_total: int
    endpoints_discovered: int
    interactions_triggered: int
    unfinished_urls: List[str]
    saturation_curve: Tuple[Dict[str, int], ...]

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


def _saturation_curve(discovery_sequence: List[Tuple[int, str]]) -> Tuple[Dict[str, int], ...]:
    """One point per interaction: how many first-party endpoints had never
    been seen before that interaction (docs/adr/0001's `endpoints.
    saturation_curve` - "the honest substitute for a percentage" with no
    known denominator for total API surface). One point per interaction,
    not a coarser bucket: the schema names the shape but not a bucket
    size, and inventing one here would be an aggregation choice this
    generator has no basis to make.
    """
    seen: set = set()
    curve = []
    for interactions_so_far, (_, endpoint_id) in enumerate(discovery_sequence, 1):
        is_new = endpoint_id not in seen
        seen.add(endpoint_id)
        curve.append({"interactions": interactions_so_far, "new_endpoints": 1 if is_new else 0})
    return tuple(curve)


def build_coverage(graph_store: Any) -> CrawlCoverage:
    """Read the site's reach from the store. Pure read, no LLM, no writes.
    Details: docs/dev/generators/coverage.md#build_coverage
    """
    pages_finished, pages_total = graph_store.count_visited()
    components_unexplored, components_total = graph_store.count_unexplored_components()
    unfinished = [
        row["url"] for row in graph_store.get_progress_table_rows() if row.get("status") != "Finished"
    ]
    return CrawlCoverage(
        pages_finished=pages_finished,
        pages_total=pages_total,
        components_explored=components_total - components_unexplored,
        components_total=components_total,
        endpoints_discovered=len(graph_store.get_inferred_requests()),
        interactions_triggered=graph_store.count_interactions(),
        unfinished_urls=sorted(unfinished),
        saturation_curve=_saturation_curve(graph_store.get_endpoint_discovery_sequence()),
    )


def _coverage_document(coverage: CrawlCoverage, request: DocumentRequest) -> Dict[str, Any]:
    """`coverage.json`'s full payload (`schemas/coverage.schema.json`,
    docs/adr/0001) - `coverage`'s graph-derived numbers plus the run-level
    facts (`run_id`/`target`/`duration_s`) `build_coverage` has no access
    to, threaded through `request.settings` by `core/engine.py`.
    `roles`/`blockers`/`module_coverage` are reserved per the ADR: minimal
    real defaults, not invented data.
    Details: docs/dev/generators/coverage.md#_coverage_document
    """
    settings = request.settings
    document: Dict[str, Any] = {
        "run_id": settings.get("run_id", ""),
        "target": settings.get("target", request.site),
        "crawler": {"engine": "pragma", "version": "dev"},
        "duration_s": settings.get("duration_s", 0.0),
        "routes": {
            "discovered": coverage.pages_total,
            "visited": coverage.pages_finished,
            "unvisited": [{"url": url, "reason": "unfinished"} for url in coverage.unfinished_urls],
        },
        "interactions": {
            "detected": coverage.components_total,
            "triggered": coverage.interactions_triggered,
        },
        "endpoints": {
            "observed": coverage.endpoints_discovered,
            "saturation_curve": list(coverage.saturation_curve),
        },
        "roles": ["anon"],
        "blockers": [],
        "module_coverage": [],
    }
    if settings.get("stopped_reason"):
        document["stopped_reason"] = settings["stopped_reason"]
    return document


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


def _render_coverage_view(coverage: CrawlCoverage, site: str) -> str:
    """`coverage.md`, mechanically rendered from `coverage`'s numbers - the
    view document ADR-0001 splits out from `coverage.json`.
    Details: docs/dev/generators/coverage.md#_render_coverage_view
    """
    lines = [
        f"# Crawl Coverage: {site}",
        "",
        PUBLIC_SURFACE_CAVEAT,
        "",
        "| Measure | Reached | Total | Coverage |",
        "|---|---|---|---|",
        f"| Pages visited | {coverage.pages_finished} | {coverage.pages_total} | {coverage.pages_percent}% |",
        f"| Components interacted with | {coverage.components_explored} | {coverage.components_total} "
        f"| {coverage.components_percent}% |",
        f"| API endpoints discovered | {coverage.endpoints_discovered} | - | - |",
        f"| Interactions triggered | {coverage.interactions_triggered} | {coverage.components_total} | - |",
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


@DOCUMENT_REGISTRY.register("coverage")
class CoverageDocument(DocumentGenerator):
    """D9: the coverage report as a document of its own - now a source
    (`coverage.json`) plus a mechanically-rendered view (`coverage.md`),
    per docs/adr/0001.
    Details: docs/dev/generators/coverage.md#coveragedocument
    """

    name = "coverage"
    title = "Crawl Coverage"
    purpose = "How much of the application this run actually reached - the ceiling on every other document."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        coverage = request.coverage or build_coverage(request.graph_store)
        document = _coverage_document(coverage, request)
        validate_against_schema(document, _SCHEMA_PATH)
        source = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        view = _render_coverage_view(coverage, request.site)
        return (
            DocumentOutput(filename="coverage", kind="source", extension="json", content=source),
            DocumentOutput(filename="coverage", kind="view", extension="md", content=view),
        )
