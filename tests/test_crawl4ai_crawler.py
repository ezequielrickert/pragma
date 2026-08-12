"""Regression tests for Crawl4AICrawler (src/crawlers/crawl4ai_crawler.py),
the Phase 1 replacement for PlaywrightScraper._discover_components.

Each case here maps to a specific, previously-fixed bug documented in
PlaywrightScraper's own docstrings / wiki/browser-automation-pitfalls.md, plus
the shadow-DOM path bug found while building this module (see the plan file's
"Phase 0 spike" section) - per wiki/debugging-agent-systems.md, a regression
test should reproduce the *specific* symptom, not just a generic smoke test.

No pytest-asyncio dependency: each test wraps its coroutine in `asyncio.run()`
directly, since these are one-off async calls, not a suite large enough to
warrant a new test dependency.
"""
import asyncio
import http.server
import threading
import time
from pathlib import Path
from typing import List

import pytest

from src.crawlers.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "discovery"


@pytest.fixture(scope="module")
def fixture_server():
    """Serve tests/fixtures/discovery/ over real local HTTP, not file:// -
    Chromium silently fails to load cross-document iframe content under
    file://, confirmed during the Phase 0 spike."""
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(FIXTURE_DIR), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()


def _discover(url: str):
    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            return await crawler.discover_page(url)

    return asyncio.run(run())


@pytest.fixture
def tracking_fixture_server():
    """Same fixture directory as `fixture_server`, but records every request
    path server-side (`requested_paths`) and sleeps before responding to
    `/slow.html` - needed for two things a plain static-file server can't
    prove: whether `block_images` actually stops a *network request* (not
    just a rendered result crawl4ai's own exclude_external_images would
    still show as "filtered" even without one - see Crawl4AICrawler's
    `block_images` docstring), and whether `page_timeout_seconds` actually
    bounds a genuinely slow-to-respond request (not the client-side-JS-delay
    case `delayed_render.html` above exercises - that's wait_seconds's job,
    a different phase). Function-scoped (not module-scoped like
    `fixture_server`) so each test gets its own clean `requested_paths` list.
    """
    requested_paths: List[str] = []

    class _TrackingHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            requested_paths.append(self.path)
            if self.path == "/slow.html":
                time.sleep(3)
            super().do_GET()

        def log_message(self, format, *args):
            pass  # quiet - this handler deliberately hangs on /slow.html

    handler = lambda *args, **kwargs: _TrackingHandler(*args, directory=str(FIXTURE_DIR), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", requested_paths
    server.shutdown()
    thread.join()


def test_zero_wait_seconds_misses_content_rendered_after_a_delay(fixture_server):
    """Regression test for the empanad.app bug (2026-08-08, found via real-
    world testing, not by any fixture in this suite): with no settle delay,
    discovery runs before delayed (SPA-hydration-style) content ever renders -
    `wait_for="css:body"` is satisfied by the pre-hydration shell alone. This
    test pins the *broken* behavior at wait_seconds=0 specifically so the fix
    below has something concrete to contrast against, not just "it works.\""""
    state = _discover(f"{fixture_server}/delayed_render.html")
    assert not any(c["text"] == "Rendered late" for c in state.components)


def test_wait_seconds_finds_content_rendered_after_a_delay(fixture_server):
    """The fix: a sufficient settle delay before discovery lets the same
    delayed content actually be found - see
    wiki/crawl4ai-integration-pitfalls.md's "wait_for=css:body is satisfied by
    the pre-hydration shell" entry."""

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=3)) as crawler:
            return await crawler.discover_page(f"{fixture_server}/delayed_render.html")

    state = asyncio.run(run())
    assert any(c["text"] == "Rendered late" for c in state.components)


def test_interaction_wait_seconds_controls_post_click_settle_delay(fixture_server):
    """interaction_wait_seconds must be consulted for the post-click
    re-discovery, independent of wait_seconds (which only applies to a plain
    navigation's own first-load wait) - see Crawl4AICrawler's docstring on
    why the two were split (a same-page DOM update settles far faster than a
    full page's first hydration in the common case, but this fixture proves
    the *short* one specifically is still governed by its own knob, not
    silently inheriting wait_seconds)."""
    url = f"{fixture_server}/delayed_reveal_on_click.html"

    async def click_with(interaction_wait_seconds: float):
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, interaction_wait_seconds=interaction_wait_seconds)) as crawler:
            await crawler.discover_page(url, session_id=url)
            return await crawler.click(url, url, "body > button#trigger")

    short_state = asyncio.run(click_with(0))
    assert not any(c["text"] == "Revealed late" for c in short_state.components)

    long_state = asyncio.run(click_with(3))
    assert any(c["text"] == "Revealed late" for c in long_state.components)


def test_wait_seconds_exits_as_soon_as_content_appears_not_the_full_ceiling(fixture_server):
    """wait_seconds/interaction_wait_seconds are a ceiling, not a flat sleep -
    `_wait_for_new_content` polls in short steps and returns the moment new
    content is found, rather than always sleeping the full configured amount.
    `delayed_render.html`'s content appears at 1.5s; a 5s ceiling must still
    finish well under 5s once it does, not just eventually return correct
    content at the full ceiling's cost."""

    async def timed_discover(ceiling: float) -> float:
        start = asyncio.get_event_loop().time()
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=ceiling)) as crawler:
            await crawler.discover_page(f"{fixture_server}/delayed_render.html")
        return asyncio.get_event_loop().time() - start

    elapsed = asyncio.run(timed_discover(5))
    # 1.5s content delay + poll granularity + real browser/extraction
    # overhead, comfortably short of the 5s ceiling it would take if this
    # were still a flat sleep.
    assert elapsed < 3.0


def test_settle_wait_survives_a_short_plateau_before_the_real_change(fixture_server):
    """Regression test for the empanad.app bug (2026-08-11, found via a real
    crawl: 0 components discovered right after clicking "Crear pedido", with
    the page markdown collapsing to 1 char - see wiki/crawl4ai-integration-
    pitfalls.md's hydration-wait entry; this is a second, later-discovered
    instance of the same failure class).

    Two versions of `_wait_for_new_content` were tried and both were wrong
    against the real site before this fixture caught it - worth recording
    both, since either mistake is easy to re-make:
    - v1 returned the instant it saw *any* change from baseline - caught the
      fixture's async loading-state toggle immediately, never saw the real
      content. Fixed by requiring the signal to hold steady for one more
      poll step.
    - v1's fix still failed against the *real* site: its intermediate
      loading-state plateau held for only ~0.13s (live-measured), shorter
      than one poll step's neighbor but long enough to satisfy "unchanged
      for exactly one 0.1s step" - so v1's fix returned on that plateau too.
      This fixture's own plateau (250ms, deliberately longer than one poll
      step but shorter than `_STABLE_HOLD_SECONDS`) reproduces that specific
      gap. The real fix requires a fixed quiet window (`_STABLE_HOLD_
      SECONDS`) after the *last* change, not just one sample of agreement.
    """
    url = f"{fixture_server}/two_stage_reveal_on_click.html"

    async def click_with(interaction_wait_seconds: float):
        async with Crawl4AICrawler(
            Crawl4AICrawlerConfig(wait_seconds=0, interaction_wait_seconds=interaction_wait_seconds)
        ) as crawler:
            await crawler.discover_page(url, session_id=url)
            return await crawler.click(url, url, "body > button#trigger")

    state = asyncio.run(click_with(3))
    assert any(c["text"] == "Revealed after fetch" for c in state.components)


def test_sibling_links_get_unique_disambiguated_paths(fixture_server):
    """Sibling <a> tags with no id/class must not collapse to the same
    selector (the original strict-mode-violation bug)."""
    state = _discover(f"{fixture_server}/index.html")
    paths = {c["path"] for c in state.components if c["text"] in ("One", "Two", "Three")}
    assert len(paths) == 3


def test_colon_in_id_is_css_escaped(fixture_server):
    """A Radix-style id containing a colon must produce a valid, resolvable
    CSS selector, not a syntax error."""
    state = _discover(f"{fixture_server}/index.html")
    match = [c for c in state.components if c["text"] == "Escaped id button"]
    assert match
    assert match[0]["path"] == r"body > button#radix-\:r0\:"


def test_shadow_root_direct_child_keeps_its_own_path_segment(fixture_server):
    """Regression test for the bug found via the crawl4ai migration spike: an
    element that is a direct child of an open shadow root must resolve to its
    own path, not silently collapse to its host's path."""
    state = _discover(f"{fixture_server}/index.html")
    match = [c for c in state.components if c["text"] == "Inside shadow root"]
    assert match
    assert match[0]["path"] == "body > div#shadow-host > button#shadowBtn"


def test_aria_role_options_discovered_while_hidden(fixture_server):
    """Custom-widget ARIA roles (role=option, etc.) must be discovered even
    while their containing popover is closed/hidden - the original
    'nothing to click' bug."""
    state = _discover(f"{fixture_server}/index.html")
    options = [c for c in state.components if c.get("role") == "option"]
    assert len(options) == 2
    assert all(not c["visible"] for c in options)


def test_mega_menu_submenu_present_but_not_visible_before_click(fixture_server):
    """A dropdown's items exist in the DOM at discovery time even though
    CSS-hidden until the trigger is interacted with."""
    state = _discover(f"{fixture_server}/index.html")
    submenu = [c for c in state.components if c["text"] in ("Sub A", "Sub B")]
    assert len(submenu) == 2
    assert not any(c["visible"] for c in submenu)


def test_iframe_content_discovered_via_per_frame_evaluate(fixture_server):
    """Content inside an <iframe> must be discovered too, tagged with its
    frame_url so click/fill can retarget the right document later."""
    state = _discover(f"{fixture_server}/index.html")
    match = [c for c in state.components if c["text"] == "Button inside iframe"]
    assert match
    assert match[0]["frame_url"]


def test_multilingual_label_recovered_without_placeholder(fixture_server):
    """A field labelled via <label for=""> with no placeholder, in a
    non-English language, must still resolve a real label - not look
    unlabelled to keyword-matching logic downstream."""
    state = _discover(f"{fixture_server}/index.html")
    match = [c for c in state.components if c["name"] == "email"]
    assert match
    assert match[0]["label"] == "Correo electrónico"


def test_no_duplicate_component_paths_on_a_real_multi_hundred_element_page():
    """End-to-end sanity check against a real, large page (not a synthetic
    fixture) - every discovered path must be unique, confirming the
    disambiguation logic holds up outside curated test markup."""
    state = _discover("https://en.wikipedia.org/wiki/Web_scraping")
    paths = [c["path"] for c in state.components]
    assert len(paths) > 100
    assert len(paths) == len(set(paths))


def test_block_images_false_by_default_still_fetches_images(tracking_fixture_server):
    """Baseline for the test below: with block_images off (the default),
    the page's <img> actually reaches the server - proves the tracking
    fixture itself works before trusting the negative assertion next."""
    base_url, requested_paths = tracking_fixture_server

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, block_images=False)) as crawler:
            return await crawler.discover_page(f"{base_url}/image_page.html")

    state = asyncio.run(run())
    assert "/pixel.png" in requested_paths
    assert any(c["text"] == "Click me" for c in state.components)


def test_block_images_true_aborts_the_image_network_request(tracking_fixture_server):
    """The actual feature: block_images must stop the image *request* from
    ever reaching the network, not just filter it out of some result field -
    unlike crawl4ai's own exclude_external_images (see block_images's
    constructor docstring for why that flag does nothing here). Component
    discovery on the rest of the page must be unaffected."""
    base_url, requested_paths = tracking_fixture_server

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, block_images=True)) as crawler:
            return await crawler.discover_page(f"{base_url}/image_page.html")

    state = asyncio.run(run())
    assert "/pixel.png" not in requested_paths
    assert any(c["text"] == "Click me" for c in state.components)


def test_page_timeout_seconds_aborts_a_genuinely_hung_request(tracking_fixture_server):
    """page_timeout_seconds must bound the raw fetch/goto itself - a
    different phase than wait_seconds (which only applies once a page has
    already loaded, see delayed_render.html's tests above). A request whose
    HTTP response never arrives within the timeout must fail loudly, not
    hang for crawl4ai's own 60s default."""
    base_url, _ = tracking_fixture_server

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, page_timeout_seconds=1)) as crawler:
            return await crawler.discover_page(f"{base_url}/slow.html")

    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_page_timeout_seconds_generous_enough_still_succeeds(tracking_fixture_server):
    """A page_timeout_seconds comfortably above the actual response delay
    must succeed normally - proves the timeout in the test above is real
    bounding behavior, not a fixture that always fails."""
    base_url, _ = tracking_fixture_server

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, page_timeout_seconds=10)) as crawler:
            return await crawler.discover_page(f"{base_url}/slow.html")

    state = asyncio.run(run())
    assert any(c["text"] == "Click me" for c in state.components)


def _click_leaving_link(base_url: str, suppress_navigation: bool):
    """Discover navigating_link.html, click the link that leaves it, then
    click the button that doesn't - the second click is what proves the
    session is still on (and still interacting with) the original page."""
    url = f"{base_url}/navigating_link.html"

    async def run():
        config = Crawl4AICrawlerConfig(wait_seconds=0, suppress_navigation=suppress_navigation)
        async with Crawl4AICrawler(config) as crawler:
            await crawler.discover_page(url, session_id=url)
            after_link = await crawler.click(url, url, "body > a#leave")
            return after_link, await crawler.resync(url, url)

    return asyncio.run(run())


def test_suppress_navigation_keeps_the_page_rendered_and_never_fetches_the_destination(
    tracking_fixture_server,
):
    """The feature: a click that would take the browser to another page is
    aborted at the network layer, so the destination is never fetched, the
    live session stays on the page being worked on, and the URL it was
    headed for comes back as a queueable fact instead."""
    base_url, requested_paths = tracking_fixture_server
    after_link, after_resync = _click_leaving_link(base_url, suppress_navigation=True)

    assert [record["url"] for record in after_link.suppressed_navigations] == [f"{base_url}/index.html"]
    assert after_link.suppressed_navigations[0]["method"] == "GET"
    assert "/index.html" not in requested_paths
    # Still the same page, still interactable - the pass never had to stop.
    assert after_link.url.endswith("/navigating_link.html")
    assert any(c["text"] == "Stay here" for c in after_resync.components)


def test_suppress_navigation_off_lets_the_click_navigate_away(tracking_fixture_server):
    """Baseline for the test above: with the flag off, the identical click
    really does fetch the destination and move the session off the page -
    proves the negative assertions above come from the suppression, not
    from a fixture that never navigates in the first place."""
    base_url, requested_paths = tracking_fixture_server
    after_link, _ = _click_leaving_link(base_url, suppress_navigation=False)

    assert after_link.suppressed_navigations == []
    assert "/index.html" in requested_paths


def test_suppress_navigation_leaves_ordinary_subresource_requests_alone(tracking_fixture_server):
    """Only top-level document navigations are aborted - a page's own
    subresources must still load, or discovery would be reading a page the
    browser never finished building."""
    base_url, requested_paths = tracking_fixture_server

    async def run():
        config = Crawl4AICrawlerConfig(wait_seconds=0, suppress_navigation=True, block_images=False)
        async with Crawl4AICrawler(config) as crawler:
            return await crawler.discover_page(f"{base_url}/image_page.html")

    state = asyncio.run(run())
    assert "/pixel.png" in requested_paths
    assert any(c["text"] == "Click me" for c in state.components)
