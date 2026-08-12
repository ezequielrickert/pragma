"""Rebuilding a crawl's frontier from what a previous session already
recorded in the graph store.
Details: docs/dev/crawlers/resume_state.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..utils.urls import route_shape

# GraphStore page statuses. A page only reaches FINISHED once its whole
# interaction pass completed uninterrupted (GraphStoreSink.record_page_finished),
# so anything else - never visited, cut short mid-pass, killed by a stop -
# is still frontier work and needs no separate bookkeeping.
# Details: docs/dev/crawlers/resume_state.md#_finished_status
_FINISHED_STATUS = "Finished"


@dataclass
class ResumePlan:
    """Everything a previous session's graph rows say about where its
    frontier stood. Purely descriptive - applying it is `MechanicalCrawler.resume`'s job.
    Details: docs/dev/crawlers/resume_state.md#resumeplan
    """

    # Navigable URLs (scheme restored) that were discovered but never finished.
    pending_urls: List[str] = field(default_factory=list)
    # route_shape() key -> how many pages of that shape already finished, so
    # max_visits_per_route_shape keeps counting across sessions instead of
    # restarting at zero. Details: docs/dev/crawlers/resume_state.md#route_shape_visits
    route_shape_visits: Dict[str, int] = field(default_factory=dict)
    finished_count: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to resume - no prior session, or one
        that already drained its frontier.
        Details: docs/dev/crawlers/resume_state.md#is_empty
        """
        return not self.pending_urls and self.finished_count == 0


def restore_frontier(rows: List[Dict[str, Any]], scheme: str) -> ResumePlan:
    """Turn one site's `GraphStore.get_progress_table_rows` output back into
    a crawlable frontier.

    Args:
        rows: every Page row for the site, each with at least `url` and
            `status`. `get_progress_table_rows` is used rather than
            `get_pending` because the finished rows are needed too - they
            carry the route-shape history that bounds a session-token route.
        scheme: `"https"` or `"http"`, taken from the run's start URL.
            Load-bearing: graph keys are `clean_url()` output, which strips
            the scheme (and a leading `www.`), so a stored key is not a
            navigable URL until one is put back. A stripped `www.` costs at
            most one redirect, which the crawler's `resolved_url` handling
            already absorbs.

    Returns:
        A `ResumePlan`. Rows are classified only by status, so a page cut
        short mid-pass is indistinguishable from one never visited - which
        is the intent: both need another pass.
    Details: docs/dev/crawlers/resume_state.md#restore_frontier
    """
    plan = ResumePlan()
    for row in rows:
        url = row.get("url")
        if not url:
            continue
        if row.get("status") == _FINISHED_STATUS:
            plan.finished_count += 1
            shape = route_shape(url)
            plan.route_shape_visits[shape] = plan.route_shape_visits.get(shape, 0) + 1
        else:
            plan.pending_urls.append(f"{scheme}://{url}")
    return plan
