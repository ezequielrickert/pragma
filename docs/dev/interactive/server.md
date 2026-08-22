# `interactive/server.py`

## module

The interactive dashboard's Flask server (ticket #151) - a local, single-site editing session
over the documents a normal crawl+docs run already produced. Plain Python string building for
every page, no Jinja templates: the same convention `dashboard/generic_template.py` already uses,
not a second one.

**Shutdown mechanism.** `werkzeug.serving.make_server()` run on its own thread, torn down via that
server's own inherited stdlib `.shutdown()` (ticket #150's own research,
`research/150-flask-shutdown-mechanism.md` on the throwaway `research/flask-shutdown-mechanism`
branch) - the classic `werkzeug.server.shutdown` environ trick was removed in Werkzeug 2.1, this
is the real, current, maintainer-confirmed replacement. `.shutdown()` must run on a thread other
than the one blocked in `serve_forever()` (the stdlib `socketserver` requirement), so the
"finalizar" route spawns a one-off thread to call it rather than calling it inline.

Verified end-to-end against a real bound socket, not just Flask's own test client (which never
exercises `make_server`/threading at all): started a real `ServerThread`, hit `/`,
`/document/<name>`, and `/finalizar` with real HTTP requests, confirmed the thread was no longer
alive after `finalizar`'s shutdown completed.

## create_app

One Flask app for one site's interactive session. `out_dir`/`site` are closed over by every route
rather than read from Flask's own request-global state - this app is never reused across sites, so
there is nothing to gain from threading them through `request`/`g`.

## ServerThread

Wraps `werkzeug.serving.make_server()` so the main process (or, once started, a request handler on
the very app it's serving) can call `.shutdown()` on it - see the module's own "Shutdown
mechanism" section for why this specific shape and not `app.run()`.

## run_interactive_server

Blocking entry point `core/interactive_cli.py::run_interactive_command` calls - starts the
server, prints where it's listening, and returns only once "finalizar" (or an external Ctrl+C) has
shut it down. Ctrl+C is caught around `.join()`, not left to propagate raw - it calls the same
`shutdown()` the "finalizar" route does, so both paths tear the server down identically rather
than one being a clean stop and the other an abrupt process kill.
