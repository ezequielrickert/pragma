"""Unit tests for Crawl4AICrawlerPool (src/crawlers/crawl4ai_crawler_pool.py).

Constructing a Crawl4AICrawler doesn't launch a browser - only __aenter__
does (see Crawl4AICrawler.__aenter__) - so these test the pool's own
least-loaded routing and throttle-sharing logic directly, with no live
browser involved, matching tests/test_target_load_throttle.py's convention.
"""
import asyncio

from src.crawlers.crawl4ai_crawler_pool import Crawl4AICrawlerPool


def test_a_session_id_sticks_to_the_same_pool_member_until_recycled():
    """A session's binding must hold for its whole life between recycles -
    within-page interaction reuse (fetch once, interact many times) depends
    on this; only close_session should ever release it."""
    pool = Crawl4AICrawlerPool(pool_size=3)

    first_call = pool._owner_for("worker-0")
    second_call = pool._owner_for("worker-0")

    assert first_call is second_call


def test_distinct_sessions_spread_across_an_idle_pool():
    """With every pool member equally idle, new sessions must still spread
    out instead of piling onto one instance - the round-robin tie-break."""
    pool = Crawl4AICrawlerPool(pool_size=3)

    owners = [pool._owner_for(f"worker-{i}") for i in range(3)]

    assert len(set(owners)) == 3  # each session landed on a distinct instance


def test_more_concurrent_sessions_than_pool_members_share_without_erroring():
    """Assignment must degrade gracefully once every pool member already has
    a session, not raise."""
    pool = Crawl4AICrawlerPool(pool_size=2)

    owners = [pool._owner_for(f"worker-{i}") for i in range(4)]

    assert len(set(owners)) == 2
    assert all(owner in pool._crawlers for owner in owners)


def test_a_new_session_is_placed_on_the_least_loaded_pool_member():
    """The whole point of moving off pure round-robin: if one pool member is
    already busy with in-flight calls, a brand-new session must land on a
    quieter one instead, regardless of arrival order."""
    pool = Crawl4AICrawlerPool(pool_size=2)
    busy, quiet = pool._crawlers
    pool._active_calls[id(busy)] = 3
    pool._active_calls[id(quiet)] = 0

    owner = pool._owner_for("worker-new")

    assert owner is quiet


def test_pool_size_below_one_still_builds_a_usable_pool():
    """A misconfigured pool_size (0 or negative) must not leave the pool
    with zero members - mirrors MechanicalCrawler's own max(1, ...) guard
    on page_concurrency."""
    pool = Crawl4AICrawlerPool(pool_size=0)

    assert len(pool._crawlers) == 1


def test_every_pool_member_shares_one_target_load_throttle():
    """The target server can't tell how many of our browser processes are
    hitting it - backoff/circuit-breaker state must be pooled, not tracked
    independently per instance, or workers on different pool members would
    never learn from each other's slowdowns."""
    pool = Crawl4AICrawlerPool(pool_size=3)

    throttles = {crawler._throttle for crawler in pool._crawlers}

    assert throttles == {pool._throttle}


def test_target_slowdown_ratio_reflects_the_shared_throttle():
    """Recording a slowdown through any one pool member's throttle must be
    visible via the pool's own target_slowdown_ratio - MechanicalCrawler
    reads this property to taper concurrency, and it must see the crawl's
    real, pooled state, not one instance's private view."""
    pool = Crawl4AICrawlerPool(pool_size=2)
    pool._throttle.record_navigation(1.0)
    pool._throttle.record_navigation(5.0)  # 5x the fastest seen - a real slowdown

    assert pool.target_slowdown_ratio == 5.0


def test_close_session_reaches_the_right_owner():
    """Recycling a worker's tab must call close_session on the pool member
    that session actually lives on, not a differently-chosen one."""
    pool = Crawl4AICrawlerPool(pool_size=2)
    original_owner = pool._owner_for("worker-0")
    closed_on: list = []

    async def fake_close_session(session_id: str) -> None:
        closed_on.append(session_id)

    original_owner.close_session = fake_close_session

    asyncio.run(pool.close_session("worker-0"))

    assert closed_on == ["worker-0"]


def test_close_session_frees_the_session_for_reassignment():
    """Unlike a still-live session (which must stay put), a recycled one's
    binding must be released - its next visit gets placed against whichever
    browser is least loaded *then*, not forced back to its old one. This is
    what lets the pool correct for two sessions on one browser turning out
    busier than sessions elsewhere, instead of that imbalance persisting for
    the rest of the crawl."""
    pool = Crawl4AICrawlerPool(pool_size=2)
    original_owner = pool._owner_for("worker-0")

    async def fake_close_session(session_id: str) -> None:
        pass

    original_owner.close_session = fake_close_session

    asyncio.run(pool.close_session("worker-0"))

    assert "worker-0" not in pool._owner_by_session


def test_active_calls_are_counted_only_for_their_duration():
    """_call must increment the owner's in-flight count while a call is
    running and decrement it once done - that's the live signal new
    sessions get balanced against."""
    pool = Crawl4AICrawlerPool(pool_size=1)
    owner = pool._crawlers[0]
    seen_during_call = None

    async def slow_call(_owner):
        nonlocal seen_during_call
        seen_during_call = pool._active_calls[id(owner)]
        return "done"

    result = asyncio.run(pool._call("worker-0", slow_call))

    assert result == "done"
    assert seen_during_call == 1  # counted while the call was in flight
    assert pool._active_calls[id(owner)] == 0  # released once it finished
