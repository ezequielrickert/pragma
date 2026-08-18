"""Regression tests for SessionRecycleGate
(spiders/browser/crawl4ai_crawler/session_recycle_gate.py) - the reader-
writer coordination between in-flight browser operations and session
recycling, added after a live austral.edu.ar deadlock traced to
close_session() racing a concurrent worker's own in-flight arun() call
against the same shared browser context.
"""
import asyncio

from spiders.browser.crawl4ai_crawler.session_recycle_gate import SessionRecycleGate


def test_two_readers_run_concurrently():
    """Readers must never serialize against each other - only a writer
    forces exclusivity."""
    gate = SessionRecycleGate()
    overlap = {"count": 0, "max": 0}

    async def reader_task():
        async with gate.reader():
            overlap["count"] += 1
            overlap["max"] = max(overlap["max"], overlap["count"])
            await asyncio.sleep(0.05)
            overlap["count"] -= 1

    async def run():
        await asyncio.gather(reader_task(), reader_task())

    asyncio.run(run())
    assert overlap["max"] == 2


def test_writer_waits_for_an_active_reader_before_proceeding():
    """A close_session (writer) entered while a page is still navigating
    (reader) must not proceed until that navigation finishes - the exact
    race confirmed live on austral.edu.ar."""
    gate = SessionRecycleGate()
    events = []

    async def reader_task():
        async with gate.reader():
            events.append("reader-start")
            await asyncio.sleep(0.05)
            events.append("reader-end")

    async def writer_task():
        await asyncio.sleep(0.01)  # start after the reader has already entered
        async with gate.writer(drain_timeout_seconds=5.0):
            events.append("writer-start")

    async def run():
        await asyncio.gather(reader_task(), writer_task())

    asyncio.run(run())
    assert events == ["reader-start", "reader-end", "writer-start"]


def test_writer_blocks_new_readers_until_it_releases():
    """Once a writer is running, a new reader must wait for it to finish -
    not run concurrently with a recycle in progress."""
    gate = SessionRecycleGate()
    events = []

    async def writer_task():
        async with gate.writer(drain_timeout_seconds=5.0):
            events.append("writer-start")
            await asyncio.sleep(0.05)
            events.append("writer-end")

    async def reader_task():
        await asyncio.sleep(0.01)  # start after the writer has already entered
        async with gate.reader():
            events.append("reader-start")

    async def run():
        await asyncio.gather(writer_task(), reader_task())

    asyncio.run(run())
    assert events == ["writer-start", "writer-end", "reader-start"]


def test_writer_gives_up_waiting_past_drain_timeout_and_proceeds_anyway(capsys):
    """A reader that never releases (a bug in some future caller not
    bounded by navigation_watchdog_seconds, since every real reader today
    is) must not stall recycling forever - the same give-up-and-proceed
    discipline WorkerPacing.wait_for_memory_headroom already uses for its
    own bounded wait."""
    gate = SessionRecycleGate()
    reader_released = asyncio.Event()

    async def stuck_reader():
        async with gate.reader():
            await reader_released.wait()

    async def run():
        reader_task = asyncio.create_task(stuck_reader())
        await asyncio.sleep(0.01)
        async with gate.writer(drain_timeout_seconds=0.1):
            pass
        reader_released.set()
        await reader_task

    asyncio.run(run())
    assert "proceeding after" in capsys.readouterr().out
