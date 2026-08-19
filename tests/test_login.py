"""Regression tests for the login orchestration hook (spiders/browser/login.py) -
the reuse/precheck/capture decision every crawl stage calls into instead of
each re-deriving it. `capture_login_session` itself is monkeypatched out in
every case: it blocks on real stdin against a real headed browser, so these
tests only prove *whether* it would have been called, not what it does.
"""
import asyncio
import http.server
import os
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import pytest

from spiders.browser.login import ensure_login_session, force_login_session
from spiders.browser.login_session import session_path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "login"


@pytest.fixture(scope="module")
def fixture_server():
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


def _sessions_dir():
    return tempfile.mkdtemp()


def test_ensure_login_session_reuses_a_valid_cached_session_without_a_precheck(
    fixture_server, monkeypatch
):
    """A fresh, valid session file short-circuits before the precheck
    browser ever opens - proven by making both the precheck's own crawler
    and capture_login_session raise if either runs."""

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("should not run with a valid cached session")

    monkeypatch.setattr("spiders.browser.login.capture_login_session", _fail_if_called)
    monkeypatch.setattr("spiders.browser.login.Crawl4AICrawler", _fail_if_called)

    sessions_dir = _sessions_dir()
    site = urlparse(fixture_server).netloc
    candidate = session_path(site, sessions_dir)
    os.makedirs(os.path.dirname(candidate), exist_ok=True)
    with open(candidate, "w", encoding="utf-8") as f:
        f.write("{}")

    result = asyncio.run(
        ensure_login_session(f"{fixture_server}/index.html", site, sessions_dir=sessions_dir)
    )
    assert result == candidate


def test_ensure_login_session_skips_capture_when_the_page_has_no_login_form(fixture_server, monkeypatch):
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("capture_login_session should not run without a login form")

    monkeypatch.setattr("spiders.browser.login.capture_login_session", _fail_if_called)

    sessions_dir = _sessions_dir()
    site = urlparse(fixture_server).netloc
    result = asyncio.run(
        ensure_login_session(f"{fixture_server}/index.html", site, sessions_dir=sessions_dir)
    )
    assert result is None
    assert not os.path.exists(session_path(site, sessions_dir))


def test_ensure_login_session_captures_when_a_login_form_is_found(fixture_server, monkeypatch):
    captured = {}

    async def _fake_capture(url, save_path, *, headless=False):
        captured["url"] = url
        captured["save_path"] = save_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("{}")

    monkeypatch.setattr("spiders.browser.login.capture_login_session", _fake_capture)

    sessions_dir = _sessions_dir()
    site = urlparse(fixture_server).netloc
    url = f"{fixture_server}/gated.html"
    result = asyncio.run(ensure_login_session(url, site, sessions_dir=sessions_dir))

    assert result == session_path(site, sessions_dir)
    assert captured["url"] == url
    assert os.path.exists(result)


def test_force_login_session_recaptures_even_with_a_valid_cached_session(fixture_server, monkeypatch):
    """`pragma login` is an explicit request to sign in - it must never
    reuse a cached session, proven by seeding a valid one and asserting
    capture_login_session still runs."""
    captured = {}

    async def _fake_capture(url, save_path, *, headless=False):
        captured["called"] = True
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("{}")

    monkeypatch.setattr("spiders.browser.login.capture_login_session", _fake_capture)

    sessions_dir = _sessions_dir()
    site = urlparse(fixture_server).netloc
    candidate = session_path(site, sessions_dir)
    os.makedirs(os.path.dirname(candidate), exist_ok=True)
    with open(candidate, "w", encoding="utf-8") as f:
        f.write("{}")

    result = asyncio.run(
        force_login_session(f"{fixture_server}/index.html", site, sessions_dir=sessions_dir)
    )
    assert result == candidate
    assert captured.get("called")
