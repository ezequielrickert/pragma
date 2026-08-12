"""Tests for rebuilding a frontier out of a previous session's graph rows
(src/crawlers/resume_state.py).

The rows here are shaped like `GraphStore.get_progress_table_rows` output:
`url` is a `clean_url()` key, so it carries no scheme - restoring one is the
whole reason a plain "read the pending list" call isn't enough.
"""
from src.crawlers.resume_state import ResumePlan, restore_frontier


def _row(url: str, status: str):
    return {"url": url, "status": status, "components": 0, "label": "-"}


def test_pending_rows_become_navigable_urls_with_the_scheme_restored():
    rows = [_row("a.com/one", "Pending"), _row("a.com/two", "Pending")]

    plan = restore_frontier(rows, "https")

    assert plan.pending_urls == ["https://a.com/one", "https://a.com/two"]


def test_http_start_url_keeps_resumed_pages_on_http():
    plan = restore_frontier([_row("127.0.0.1:8000/page", "Pending")], "http")

    assert plan.pending_urls == ["http://127.0.0.1:8000/page"]


def test_finished_rows_are_counted_but_never_requeued():
    rows = [_row("a.com/done", "Finished"), _row("a.com/todo", "Pending")]

    plan = restore_frontier(rows, "https")

    assert plan.pending_urls == ["https://a.com/todo"]
    assert plan.finished_count == 1


def test_finished_rows_carry_their_route_shape_history_forward():
    """Two finished pages of one token-shaped route must still read as two
    visits of that shape next session, or max_visits_per_route_shape starts
    over from zero on every resume and the bound never actually holds."""
    rows = [
        _row("a.com/o/aB3xK9mQ7pL2wR5t", "Finished"),
        _row("a.com/o/zY8nH4vC1jF6dS0g", "Finished"),
        _row("a.com/about", "Finished"),
    ]

    plan = restore_frontier(rows, "https")

    assert plan.route_shape_visits == {"a.com/o/{token}": 2, "a.com/about": 1}


def test_a_page_cut_short_mid_pass_is_indistinguishable_from_an_unvisited_one():
    """Neither reached Finished, so both are frontier work - the point of
    keying off status rather than tracking interruptions separately."""
    rows = [_row("a.com/interrupted", "Pending"), _row("a.com/never-seen", "Pending")]

    plan = restore_frontier(rows, "https")

    assert plan.pending_urls == ["https://a.com/interrupted", "https://a.com/never-seen"]


def test_rows_without_a_url_are_skipped_rather_than_crashing_the_resume():
    plan = restore_frontier([{"status": "Pending"}, _row("a.com/real", "Pending")], "https")

    assert plan.pending_urls == ["https://a.com/real"]


def test_a_site_with_no_recorded_history_reads_as_nothing_to_resume():
    assert restore_frontier([], "https").is_empty


def test_a_fully_drained_previous_session_is_not_empty():
    """finished_count alone must keep is_empty false: those pages still need
    to be skipped rather than recrawled."""
    plan = restore_frontier([_row("a.com/done", "Finished")], "https")

    assert not plan.is_empty
    assert plan.pending_urls == []


def test_a_default_plan_carries_nothing():
    assert ResumePlan().is_empty
