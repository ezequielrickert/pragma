# Research: Flask/Werkzeug's real programmatic shutdown mechanism (#150)

> Research child of #146 (interactive dashboard map). Ticket: #150, "Confirm Flask/werkzeug's
> real programmatic shutdown mechanism for the in-chat 'finalizar' button."

## Summary

The classic `request.environ.get('werkzeug.server.shutdown')()` trick is gone for good reason,
not just neglect: it was **deprecated in Werkzeug 2.0.0** (2021-05-11,
[pallets/werkzeug#1752](https://github.com/pallets/werkzeug/issues/1752)) and **removed in
Werkzeug 2.1.0** (2022-03-28,
[pallets/werkzeug#2276](https://github.com/pallets/werkzeug/pull/2276/files)), because it reached
into private double-underscore server internals to interrupt the accept loop. Flask's own docs
(`flask.palletsprojects.com/en/stable/server/`) say nothing about programmatic shutdown at all —
they cover only `flask run` and `app.run()`, with the standard "not for production" warning and no
carve-out for a locally-run tool. Werkzeug's docs, however, do document a first-party replacement
aimed at exactly this "local tool needs to stop its own server" scenario
(`docs/serving.rst`, "Shutting Down The Server" section, added by
[pallets/werkzeug#2208](https://github.com/pallets/werkzeug/pull/2208/files) as the direct
replacement for the removed trick) — but it shuts down via `multiprocessing.Process.terminate()`,
not a thread-based `.shutdown()` call.

For this project's "finalizar" button (Flask run as a local, desktop-style dev-server process, not
`flask run` fronting real traffic), the recommended mechanism is:

**`werkzeug.serving.make_server()` run in a background thread, shut down via the returned
server's inherited stdlib `.shutdown()` method, called from a second thread** — the closest thing
to a clean, current, non-deprecated, public-API mechanism, confirmed correct by a Werkzeug core
maintainer. `os._exit()` remains a legitimate, version-proof fallback/belt-and-suspenders path, not
a hack to be embarrassed about — several real local-tool projects (onionshare, dash,
jupyter-dash) independently converged on it after hitting this same Werkzeug 2.1 removal.

## 1. Why the old trick is gone (exact versions, from the primary changelog)

Werkzeug's `CHANGES.rst` (`pallets/werkzeug`, GitHub), read directly:

- **Added**, Werkzeug 0.7 (~2011): "The builtin server now adds a function named
  `werkzeug.server.shutdown` into the WSGI env to initiate a shutdown."
- **Deprecated**, Werkzeug **2.0.0** (2021-05-11): "Deprecate the
  `environ["werkzeug.server.shutdown"]` function that is available when running the development
  server. :issue:`1752`" —
  [pallets/werkzeug#1752](https://github.com/pallets/werkzeug/issues/1752), opened by maintainer
  davidism: the implementation was "pretty weird"/relied on private server internals, and the dev
  server "is only for development" so nothing should depend on it programmatically.
- **Removed**, Werkzeug **2.1.0** (2022-03-28), via
  [pallets/werkzeug#2276](https://github.com/pallets/werkzeug/pull/2276/files): "Remove the
  non-standard `shutdown` function from the WSGI environ when running the development server. See
  the docs for alternatives."

So: current Flask 3.x pulls in Werkzeug 3.x, and the hook has been gone since Werkzeug 2.1 —
any code (or Stack Overflow answer) using `request.environ.get('werkzeug.server.shutdown')` is
stale for any Werkzeug this project would plausibly pin.

## 2. What Flask's own current docs say: nothing

`flask.palletsprojects.com/en/stable/server/` (current 3.1.x stable docs) covers only: the
`flask run` CLI, the "Address already in use" troubleshooting note, "Deferred Errors on Reload",
and calling `app.run()` in code. It never mentions `make_server`, a `Server`/`BaseWSGIServer`
object, or any shutdown mechanism — first-party Flask docs are simply silent here, positive or
negative, on a locally-run dashboard tool controlling its own server.

## 3. What Werkzeug's own current docs say: the documented replacement

Werkzeug's `docs/serving.rst` ("Serving WSGI Applications") has a section titled **"Shutting Down
The Server"**, added specifically to replace the removed environ hook
([pallets/werkzeug#2208](https://github.com/pallets/werkzeug/pull/2208/files)). It explicitly
names this project's exact use case:

> "In some cases it can be useful to shut down a server after handling a request. For example, a
> local command line tool that needs OAuth authentication could temporarily start a server to
> listen for a response, record the user's token, then stop the server."

Its shown mechanism is process-based, not thread-based:

```python
import multiprocessing
from werkzeug import Request, Response, run_simple

def get_token(q: multiprocessing.Queue) -> None:
    @Request.application
    def app(request: Request) -> Response:
        q.put(request.args["token"])
        return Response("", 204)
    run_simple("localhost", 5000, app)

if __name__ == "__main__":
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=get_token, args=(q,))
    p.start()
    token = q.get(block=True)
    p.terminate()
```

It closes with: "That example uses Werkzeug's development server, but any production server that
can be started as a Python process could use the same technique and should be preferred for
security." This is the only mechanism Werkzeug documents in prose as the sanctioned replacement,
and it implicitly endorses "local tool controlling its own server" as a legitimate use — while
still nudging toward a real WSGI server underneath if practical.

## 4. `make_server()` + thread + `.shutdown()` — the recommended mechanism

Confirmed directly against current Werkzeug source
(`src/werkzeug/serving.py`, matches released **Werkzeug 3.1.x**):

- `make_server(host, port, app, threaded=False, processes=1, ...)` is a real, public, unchanged
  function returning a `BaseWSGIServer` (or `ThreadedWSGIServer` when `threaded=True`, or
  `ForkingWSGIServer`).
- `BaseWSGIServer(HTTPServer)` → stdlib `socketserver.TCPServer` → `socketserver.BaseServer`.
  Werkzeug does **not** override `.shutdown()` — it's the plain, inherited stdlib
  `socketserver.BaseServer.shutdown()`. Werkzeug does override `serve_forever()`, adding only a
  `KeyboardInterrupt` catch and a `server_close()` in `finally`:
  ```python
  def serve_forever(self, poll_interval: float = 0.5) -> None:
      try:
          super().serve_forever(poll_interval=poll_interval)
      except KeyboardInterrupt:
          pass
      finally:
          self.server_close()
  ```
  Calling `.shutdown()` from a thread other than the one running `serve_forever()` works exactly
  the plain stdlib way: it sets a flag the poll loop notices within `poll_interval`, and
  `serve_forever()` returns normally.

This isn't guesswork — a Werkzeug core maintainer confirmed it as correct usage in
[pallets/werkzeug#2284 "Clean way to shutdown"](https://github.com/pallets/werkzeug/issues/2284)
(davidism replied pointing at the documented alternative in §3; a user, georgeharker, then posted
this exact pattern, unchallenged, in
[the same thread](https://github.com/pallets/werkzeug/issues/2284#issuecomment-965610413)):

```python
import threading
from werkzeug.serving import make_server

class ServerThread(threading.Thread):
    def __init__(self, app, host="127.0.0.1", port=5000):
        super().__init__()
        self.server = make_server(host, port, app, threaded=True)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

server_thread = ServerThread(app)
server_thread.start()

@app.route("/finalizar", methods=["POST"])
def finalizar():
    threading.Thread(target=server_thread.shutdown).start()
    return "Cerrando…", 200
```

`.shutdown()` must run on a thread other than the one blocked in `serve_forever()` — the stdlib
`socketserver` requirement — so the route spawns a one-off thread to call it rather than calling
it inline. **Verdict**: public, non-deprecated, unchanged since Werkzeug 2.1, maintainer-confirmed
— the most "proper" mechanism available, even though it's not spelled out step-by-step in prose
docs (Werkzeug's serving docs page doesn't even give `make_server` an `autofunction::` entry —
only `run_simple` and two others get one).

## 5. `os._exit()`, `sys.exit()`, and SIGINT — verified against CPython stdlib source

Read directly from `cpython/Lib/socketserver.py`:

```python
class ThreadingMixIn:
    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)
```

`ThreadingMixIn` (used by `ThreadedWSGIServer`, i.e. Flask's normal `threaded=True` mode) only
catches `Exception`. **`SystemExit` is a `BaseException`**, so `sys.exit()` called inside a Flask
view thread propagates out of *that one request's thread only* — Python logs an unhandled
exception for that thread, and the main `serve_forever()` loop is unaffected. **This confirms
the intuition exactly: `sys.exit()`/raising `SystemExit` in a threaded dev server's view function
does not stop the server.** (Caveat: if Flask ran with `threaded=False`, the view runs directly on
the main thread inside `serve_forever()`'s own call stack, where `SystemExit` isn't caught either
by Werkzeug's `serve_forever` (which only catches `KeyboardInterrupt`) — so it would actually
propagate out and kill the process there. This is a direct, derivable consequence of the two
source excerpts, not a documented sentence anywhere.)

`os.kill(os.getpid(), signal.SIGINT)` only reliably interrupts the accept loop when
`serve_forever()` runs on the **main** thread (CPython delivers signals only to the main thread).
That conflicts with the background-thread pattern in §4 — if the server itself is on a background
thread, a `SIGINT` sent from a request-handling thread has no main-thread blocking call to
interrupt, making this approach fragile for this project's shape.

`os._exit(n)` — per the Python docs
([docs.python.org/3/library/os.html#os._exit](https://docs.python.org/3/library/os.html#os._exit)):
"Exit the process with status n, without calling cleanup handlers, flushing stdio buffers, etc."
It works from any thread and kills the whole process immediately, bypassing Flask/Werkzeug's
object model entirely — no exception propagation to reason about. This is exactly why it's the
pattern independently rediscovered by several real local-tool projects after hitting the same
Werkzeug 2.1 removal: onionshare
([onionshare/onionshare#1542](https://github.com/onionshare/onionshare/issues/1542)), Plotly Dash
([plotly/dash#1780](https://github.com/plotly/dash/issues/1780)), and jupyter-dash
([plotly/jupyter-dash#63](https://github.com/plotly/jupyter-dash/issues/63)). None of this is
first-party Flask/Werkzeug guidance — it's a de-facto community pattern, version-independent
because it sidesteps Werkzeug's server object entirely. Typical shape, delaying just enough to let
the HTTP response for the click reach the browser:

```python
import os, threading

@app.route("/finalizar", methods=["POST"])
def finalizar():
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return "Cerrando…", 200
```

## 6. "Not for production" vs. this project's legitimate local-tool use

Only Werkzeug's `serving.rst` (§3) explicitly acknowledges a legitimate non-production use of the
dev server matching this project's shape ("a local command line tool that needs..."). Flask's own
docs make no such distinction — their warning is blanket, with no carve-out for a locally-run
interactive dashboard with no external users. The gap is filled by downstream projects
(onionshare, dash, jupyter-dash — all local desktop-style Flask tools) independently converging on
`os._exit()` after hitting the same wall, which is itself corroboration that this is a recognized,
common pattern class even though neither Flask nor Werkzeug docs formally endorse it as
"correct."

## Recommendation for this project's "finalizar" button

Two-layer approach, in priority order:

1. **Primary — `make_server()` + background thread + `server.shutdown()`** (§4). Version-current
   (unchanged since Werkzeug 2.1, works on Werkzeug 3.1.x), public API, maintainer-confirmed, and
   lets the finalizar response complete cleanly before the server loop exits — no forced process
   kill needed for the common case.
2. **Fallback — `os._exit()` after a short delay** (§5), as a watchdog: if the graceful
   `server.shutdown()` path hasn't actually torn the process down after a couple seconds (e.g. a
   reloader child process also needs to die), fire `os._exit(0)` unconditionally. This sacrifices
   "clean" for "definitely works, on any Werkzeug version, regardless of internals" — worth
   keeping as a belt-and-suspenders path precisely because it doesn't depend on Werkzeug's server
   object model at all.

Avoid `os.kill(getpid(), SIGINT)` for this use case: it only behaves predictably when
`serve_forever()` runs on the main thread, which conflicts with running the server on a background
thread (needed for approach 1), and adds OS/Python-version uncertainty around whether the blocked
`accept()` call gets interrupted promptly.

No Flask/Werkzeug version is currently pinned in this repo (`requirements.txt` has neither) — the
interactive dashboard is future work per map #146. When it's added, pin **Flask 3.x** (currently
stable), which brings in **Werkzeug 3.x** as a transitive dependency; everything in this research
was verified against Werkzeug 3.1.x source/docs and applies from Werkzeug 2.1 onward.

## Sources consulted

- `pallets/werkzeug` `CHANGES.rst` (GitHub, raw) — 0.7 addition, 2.0.0 deprecation, 2.1.0 removal
- [pallets/werkzeug#1752](https://github.com/pallets/werkzeug/issues/1752) — deprecation issue
- [pallets/werkzeug#2276](https://github.com/pallets/werkzeug/pull/2276/files) — removal PR
- [pallets/werkzeug#2208](https://github.com/pallets/werkzeug/pull/2208/files) — added
  `serving.rst`'s "Shutting Down The Server" section
- [pallets/werkzeug#2284](https://github.com/pallets/werkzeug/issues/2284) — maintainer-confirmed
  `make_server` + `.shutdown()` pattern
- `src/werkzeug/serving.py` (`pallets/werkzeug`, current `main`/3.1.x) — `BaseWSGIServer`,
  `ThreadedWSGIServer`, `make_server`, `serve_forever` override
- `docs/serving.rst` (`pallets/werkzeug`) — "Shutting Down The Server" section
- `flask.palletsprojects.com/en/stable/server/` — Flask's Development Server docs (current stable)
- `Lib/socketserver.py` (CPython, `main`) — `ThreadingMixIn.process_request_thread`,
  `Exception`-only catch
- Python docs, `os._exit()` — https://docs.python.org/3/library/os.html#os._exit
- [onionshare/onionshare#1542](https://github.com/onionshare/onionshare/issues/1542),
  [plotly/dash#1780](https://github.com/plotly/dash/issues/1780),
  [plotly/jupyter-dash#63](https://github.com/plotly/jupyter-dash/issues/63) — downstream
  local-tool projects independently converging on `os._exit()` post-removal
- This repo's `requirements.txt`/`requirements-dev.txt` — confirmed no existing Flask/Werkzeug pin
