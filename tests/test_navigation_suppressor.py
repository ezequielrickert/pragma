"""Which requests NavigationSuppressor aborts, and which it must not.

The end-to-end behaviour (a real click, a real abort, a page that stays
rendered) is covered against real Chromium in
tests/test_crawl4ai_crawler.py. This module covers the decision itself in
isolation, since the cases that matter most are the ones a fixture page
can't easily produce on demand: an iframe navigating itself, a
service-worker request with no frame at all, and a disarmed page that must
be free to navigate normally.
"""
from src.crawlers.navigation_suppressor import NavigationSuppressor


class _FakeFrame:
    pass


class _FakePage:
    def __init__(self) -> None:
        self.main_frame = _FakeFrame()


class _FakeRequest:
    def __init__(self, url, frame, resource_type="document", method="GET", navigation=True):
        self.url = url
        self.resource_type = resource_type
        self.method = method
        self._frame = frame
        self._navigation = navigation

    @property
    def frame(self):
        if self._frame is None:
            raise Exception("Request is issued by a service worker")  # Playwright's own behaviour
        return self._frame

    def is_navigation_request(self):
        return self._navigation


def _armed_page():
    page = _FakePage()
    NavigationSuppressor.arm(page, "worker-0")
    return page


def test_top_level_navigation_is_aborted_and_recorded():
    suppressor = NavigationSuppressor()
    page = _armed_page()
    request = _FakeRequest("http://site/next", page.main_frame)

    assert suppressor.intercept(page, request) is True
    assert suppressor.take("worker-0") == [{"url": "http://site/next", "method": "GET"}]
    # take() drains, so the next interaction starts from nothing.
    assert suppressor.take("worker-0") == []


def test_a_disarmed_page_navigates_freely():
    """A real goto() runs with suppression disarmed - aborting there would
    stop the crawl from ever loading a page at all."""
    suppressor = NavigationSuppressor()
    page = _FakePage()
    NavigationSuppressor.disarm(page)

    assert suppressor.intercept(page, _FakeRequest("http://site/next", page.main_frame)) is False
    assert suppressor.take("worker-0") == []


def test_an_iframe_navigating_itself_is_left_alone():
    """An iframe re-navigating leaves the outer page - and every selector
    built against it - intact, so suppressing it would cost coverage for no
    benefit (discovery runs per-frame, see discover_components.js)."""
    suppressor = NavigationSuppressor()
    page = _armed_page()

    assert suppressor.intercept(page, _FakeRequest("http://site/embed", _FakeFrame())) is False


def test_subresources_and_non_navigation_documents_are_left_alone():
    suppressor = NavigationSuppressor()
    page = _armed_page()

    xhr = _FakeRequest("http://site/api", page.main_frame, resource_type="xhr")
    prefetched = _FakeRequest("http://site/next", page.main_frame, navigation=False)
    assert suppressor.intercept(page, xhr) is False
    assert suppressor.intercept(page, prefetched) is False


def test_a_frameless_request_is_left_alone():
    """Playwright raises rather than returning None when a request has no
    frame (service worker); that can't navigate the page either."""
    suppressor = NavigationSuppressor()
    page = _armed_page()

    assert suppressor.intercept(page, _FakeRequest("http://site/sw", None)) is False


def test_the_method_is_recorded_so_a_post_target_is_not_refetched_as_a_get():
    suppressor = NavigationSuppressor()
    page = _armed_page()
    suppressor.intercept(page, _FakeRequest("http://site/submit", page.main_frame, method="post"))

    assert suppressor.take("worker-0") == [{"url": "http://site/submit", "method": "POST"}]


def test_each_session_keeps_its_own_record():
    """Several workers share one browser process in a pooled crawl - one
    worker's aborted navigation must never surface in another's PageState."""
    suppressor = NavigationSuppressor()
    page_a, page_b = _FakePage(), _FakePage()
    NavigationSuppressor.arm(page_a, "worker-0")
    NavigationSuppressor.arm(page_b, "worker-1")

    suppressor.intercept(page_a, _FakeRequest("http://site/a", page_a.main_frame))
    suppressor.intercept(page_b, _FakeRequest("http://site/b", page_b.main_frame))

    assert suppressor.take("worker-0") == [{"url": "http://site/a", "method": "GET"}]
    assert suppressor.take("worker-1") == [{"url": "http://site/b", "method": "GET"}]
