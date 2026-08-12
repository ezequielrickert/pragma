"""Tests for the session-budget decisions behind stopping a crawl early
(src/crawlers/crawl_stopper.py)."""
import asyncio

from src.crawlers.crawl_stopper import CrawlStopper, SessionBudget, StopReason


def test_an_unbudgeted_session_never_stops_on_its_own():
    stopper = CrawlStopper()

    for _ in range(100):
        stopper.record_page_visited()

    assert not stopper.should_stop()
    assert stopper.reason is None


def test_the_page_budget_stops_the_session_on_the_page_that_spends_it():
    stopper = CrawlStopper(SessionBudget(stop_after_pages=3))

    stopper.record_page_visited()
    stopper.record_page_visited()
    assert not stopper.should_stop()

    stopper.record_page_visited()
    assert stopper.reason is StopReason.PAGE_BUDGET


def test_the_first_reason_wins_when_another_trigger_fires_during_the_stop():
    stopper = CrawlStopper(SessionBudget(stop_after_pages=1))

    stopper.record_page_visited()
    stopper.request_stop(StopReason.RATE_LIMITED)

    assert stopper.reason is StopReason.PAGE_BUDGET


def test_rate_limit_trips_stop_the_session_once_they_reach_the_budget():
    stopper = CrawlStopper(SessionBudget(stop_after_rate_limit_trips=2))

    stopper.record_rate_limit_trips(1)
    assert not stopper.should_stop()

    stopper.record_rate_limit_trips(2)
    assert stopper.reason is StopReason.RATE_LIMITED


def test_a_zero_trip_budget_disables_the_rate_limit_exit():
    """0 has to mean "off" as well as None: --stop-after-rate-limit-trips 0
    is the only way a config layer that reads None as "unset" can say it."""
    stopper = CrawlStopper(SessionBudget(stop_after_rate_limit_trips=0))

    stopper.record_rate_limit_trips(99)

    assert not stopper.should_stop()


def test_a_none_trip_budget_disables_the_rate_limit_exit():
    stopper = CrawlStopper(SessionBudget(stop_after_rate_limit_trips=None))

    stopper.record_rate_limit_trips(99)

    assert not stopper.should_stop()


def test_the_time_budget_stops_a_session_that_is_doing_nothing():
    """The deadline runs on a timer rather than being polled by workers, so
    it still fires while every worker sits idle on an empty frontier."""
    stopper = CrawlStopper(SessionBudget(stop_after_seconds=0.05))

    async def run():
        stopper.begin()
        await asyncio.wait_for(stopper.wait(), timeout=1.0)

    asyncio.run(run())

    assert stopper.reason is StopReason.TIME_BUDGET


def test_closing_cancels_a_time_budget_that_has_not_fired():
    stopper = CrawlStopper(SessionBudget(stop_after_seconds=0.05))

    async def run():
        stopper.begin()
        stopper.close()
        await asyncio.sleep(0.1)

    asyncio.run(run())

    assert not stopper.should_stop()


def test_close_is_safe_when_begin_never_ran():
    CrawlStopper(SessionBudget(stop_after_seconds=1.0)).close()


def test_wait_returns_as_soon_as_a_stop_is_requested():
    stopper = CrawlStopper()

    async def run():
        waiter = asyncio.create_task(stopper.wait())
        await asyncio.sleep(0)
        stopper.request_stop(StopReason.INTERRUPT)
        await asyncio.wait_for(waiter, timeout=1.0)

    asyncio.run(run())

    assert stopper.reason is StopReason.INTERRUPT
