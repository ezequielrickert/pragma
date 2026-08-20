"""Unit test for spiders/content/accessibility_snapshot.py's own contract
- the one part of it testable without a live Playwright page: a capture
failure must degrade to empty strings, never raise into the discovery
pass that called it."""
import asyncio

from spiders.content.accessibility_snapshot import capture_accessibility_snapshot


class _RaisingLocator:
    async def aria_snapshot(self):
        raise RuntimeError("simulated capture failure")


class _RaisingPage:
    url = "https://example.com/"

    def locator(self, selector):
        return _RaisingLocator()


def test_a_capture_failure_degrades_to_empty_strings():
    aria_snapshot_yaml, axtree_json = asyncio.run(capture_accessibility_snapshot(_RaisingPage()))

    assert (aria_snapshot_yaml, axtree_json) == ("", "")
