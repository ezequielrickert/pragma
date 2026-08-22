"""Real bound-socket tests of `interactive/server.py::ServerThread`'s
own threading/shutdown lifecycle (ticket #157) - a Flask test client
never exercises `make_server`/`ThreadingMixIn` at all, so this needs a
real server on a real port, unlike every route test in
`test_interactive_server.py`."""
import threading
import time

import requests
from flask import Flask

from interactive.server import ServerThread

PORT = 5199


def _slow_app(started: threading.Event, delay_s: float) -> Flask:
    """A minimal Flask app with one endpoint that takes `delay_s` to
    respond - stands in for a real in-flight save/chat request without
    adding test-only delay logic to any real route."""
    app = Flask(__name__)

    @app.route("/slow")
    def slow():
        started.set()
        time.sleep(delay_s)
        return "done"

    return app


def test_shutdown_waits_for_an_in_flight_request_to_finish():
    """The core of ticket #157's decision: shutdown() drains rather
    than abandoning a request already being handled. `delay_s` is
    deliberately well past werkzeug's own ~0.5s serve_forever() poll
    interval - too short a delay can't tell "genuinely drained" apart
    from "just landed on the next poll cycle by coincidence" (a real
    false-positive this test hit during development)."""
    started = threading.Event()
    thread = ServerThread(_slow_app(started, delay_s=1.5), port=PORT)
    thread.start()

    responses = []
    request_thread = threading.Thread(target=lambda: responses.append(requests.get(f"http://127.0.0.1:{PORT}/slow")))
    request_thread.start()
    started.wait(timeout=2)  # don't shut down before the slow request has even started

    shutdown_started = time.monotonic()
    thread.shutdown()
    thread.join(timeout=5)  # run() only returns once server_close() has drained the request
    shutdown_duration = time.monotonic() - shutdown_started
    request_thread.join(timeout=2)

    assert shutdown_duration >= 1.4  # genuinely waited for the in-flight request, not just polling jitter
    assert len(responses) == 1 and responses[0].text == "done"  # the client got the real response, not a reset


def test_shutdown_leaves_the_thread_not_alive():
    thread = ServerThread(_slow_app(threading.Event(), delay_s=0), port=PORT + 1)
    thread.start()

    thread.shutdown()
    thread.join(timeout=2)

    assert not thread.is_alive()
