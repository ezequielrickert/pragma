"""Prototype for issue #57: what should the mode-gate's synthetic `fulfill()`
response look like so a blocked mutating request reads as an ordinary
success to the page's own JS, instead of tripping a spinner/toast/exception
into a visible error state?

Runs a real Playwright browser (not crawl4ai - the question is about
Playwright's `route.fulfill()` itself) against
`tests/fixtures/mechanical/mutation_response_handling.html`, a fixture with
the two client-side response-handling shapes this repo's real target sites
mix: a POST whose JS awaits a JSON body and reads a field back out of it,
and a DELETE that only checks `response.ok`. Two candidate fulfill bodies
are compared; the second test exists to document *why* the first shape was
chosen, not to prove the second is safe to use.
"""
import asyncio
import http.server
import threading
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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


async def _run_against_fulfill_body(fixture_server, *, status: int, body: str) -> dict:
    """Loads the fixture, fulfills every mutating request with `(status,
    body)`, drives both the create-form submit and the delete-button click,
    and returns each interaction's final status text plus any page errors
    (uncaught exceptions) the console surfaced - the two signals the ticket
    asks to watch for ("stuck spinners, toast errors, JS exceptions").
    """
    page_errors = []

    async def fulfill_mutations(route):
        if route.request.method in _MUTATING_METHODS:
            await route.fulfill(status=status, content_type="application/json", body=body)
        else:
            await route.continue_()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        await page.route("**/api/**", fulfill_mutations)
        await page.goto(f"{fixture_server}/mutation_response_handling.html")

        await page.click("#createForm button[type=submit]")
        await page.wait_for_function(
            "document.getElementById('createStatus').textContent !== 'idle' "
            "&& document.getElementById('createStatus').textContent !== 'submitting'"
        )
        create_status = await page.text_content("#createStatus")

        await page.click("#deleteButton")
        await page.wait_for_function(
            "document.getElementById('deleteStatus').textContent !== 'idle' "
            "&& document.getElementById('deleteStatus').textContent !== 'deleting'"
        )
        delete_status = await page.text_content("#deleteStatus")

        await browser.close()

    return {"create_status": create_status, "delete_status": delete_status, "page_errors": page_errors}


def test_empty_json_object_reads_as_success_with_no_exceptions(fixture_server):
    """The chosen v1 shape: `200 {}`. Neither interaction throws - the DELETE
    button only checks `response.ok`, and the create form's `response.json()`
    call succeeds against `{}` (an empty object is still valid JSON), it just
    reads `data.id`/`data.name` back as `undefined`. That's the real trade-off
    of a single generic shape: no error state, but a cosmetically odd label
    instead of a real value - acceptable for v1 per this ticket's answer.
    """
    result = asyncio.run(_run_against_fulfill_body(fixture_server, status=200, body="{}"))

    assert result["page_errors"] == []
    assert result["create_status"] == "created #undefined: undefined"
    assert result["delete_status"] == "deleted"


def test_204_no_content_throws_on_the_json_reading_path(fixture_server):
    """Documents the pitfall a naive "just return 204" choice would hit:
    `response.json()` on an empty body raises a SyntaxError, which the
    create form's own try/catch turns into a visible "exception: ..."
    status - exactly the tripped-into-an-error-state outcome #57 exists to
    avoid. `204` is fine for the DELETE path (no body ever read) but wrong
    as the *one* generic shape every mutating method gets - the reason v1
    settles on `200 {}` instead, per the previous test.
    """
    result = asyncio.run(_run_against_fulfill_body(fixture_server, status=204, body=""))

    assert result["create_status"].startswith("exception:")
    assert result["delete_status"] == "deleted"
