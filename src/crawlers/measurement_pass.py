"""The measurement pass: re-visit an already-crawled site with a browser
configured to represent a user, not to be fast.

Why it is a second pass and not part of the crawl. The crawl's browser
runs at 800x600 with `light_mode`, `memory_saving_mode` and images, media
and fonts blocked - every one of those is a deliberate speed decision, and
together they make anything measured through it unrepresentative. Making
the crawl faithful instead would slow down the part of the pipeline that
already dominates wall-clock time, to serve documents that are a small
fraction of the value.

So: leave the crawl alone, and afterwards walk the pages it found once
more, with images on and a viewport a person would use. It only navigates
- no clicking, no filling, no frontier - which is why it costs a fraction
of the crawl rather than doubling it.

Details: docs/dev/crawlers/measurement_pass.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Tuple

from ..core.interfaces import GraphStore
from .crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig

# What a person's browser looks like, versus the crawl's 800x600.
MEASUREMENT_VIEWPORT = (1280, 800)


@dataclass(frozen=True)
class MeasurementResult:
    """What one measurement pass reached, and what it could not.
    Details: docs/dev/crawlers/measurement_pass.md#measurementresult
    """

    measured: Tuple[str, ...]
    skipped_shaped_routes: Tuple[str, ...]


def _navigable(page_url: str) -> bool:
    """Whether a stored page key can be navigated back to.

    Page nodes are keyed by `route_shape`, so a page whose path held an
    opaque token is stored as `example.com/o/{token}` - a shape, not an
    address. Those cannot be re-visited: the literal URL is not persisted
    anywhere. They are reported rather than dropped quietly.
    Details: docs/dev/crawlers/measurement_pass.md#_navigable
    """
    return "{" not in page_url


def _pages_to_measure(graph_store: GraphStore, site: str) -> Tuple[List[str], List[str]]:
    finished = [
        row["url"]
        for row in graph_store.get_progress_table_rows(site)
        if row.get("status") == "Finished"
    ]
    return [url for url in finished if _navigable(url)], [url for url in finished if not _navigable(url)]


async def run_measurement_pass(graph_store: GraphStore, site: str, headless: bool = True) -> MeasurementResult:
    """Re-visit `site`'s finished pages and record their accessibility audit.

    Args:
        graph_store: the store the crawl wrote to; read for which pages
            exist, written back with each page's violations.
        site: which site to measure.
        headless: same meaning as everywhere else in this project.

    Returns:
        A `MeasurementResult`. One navigation per page, no interaction -
        every page is already a distinct `route_shape` in the graph
        (`max_visits_per_route_shape` sees to that during the crawl), so
        visiting each one *is* the sampled pass rather than an exhaustive
        one.

        A page that fails to load is skipped with a warning rather than
        aborting: the pass is an enhancement, and losing it entirely
        because one page 500s would be a poor trade.
    Details: docs/dev/crawlers/measurement_pass.md#run_measurement_pass
    """
    navigable, shaped = _pages_to_measure(graph_store, site)
    if not navigable:
        return MeasurementResult(measured=(), skipped_shaped_routes=tuple(shaped))

    config = Crawl4AICrawlerConfig(
        headless=headless,
        # The three things that make this pass worth running at all.
        block_images=False,
        viewport_width=MEASUREMENT_VIEWPORT[0],
        viewport_height=MEASUREMENT_VIEWPORT[1],
        audit_accessibility=True,
    )
    measured: List[str] = []
    async with Crawl4AICrawler(config) as crawler:
        for page_url in navigable:
            try:
                state = await crawler.discover_page(f"https://{page_url}")
            except Exception as exc:  # noqa: BLE001 - one bad page must not cost the pass
                print(f"Measurement pass: could not re-visit {page_url}: {exc}")
                continue
            graph_store.record_accessibility_violations(
                site, page_url, json.dumps(state.accessibility_violations)
            )
            graph_store.record_page_measurements(
                site, page_url,
                json.dumps({"pseudo_styles": state.pseudo_styles, "tab_order": state.tab_order}),
            )
            measured.append(page_url)
    return MeasurementResult(measured=tuple(measured), skipped_shaped_routes=tuple(shaped))
