# `interactive/server.py`

## module

The interactive dashboard's Flask app factory and server lifecycle (ticket #151) - routing and the
server's own start/stop, not rendering. Every page's own HTML moved to `interactive/pages.py` in
ticket #154, once this file crossed `file-size-audit`'s own 300-line WATCH threshold - see that
module's own docstring for why.

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

**Chat (ticket #153).** A panel on the document's own edit page, not a separate route -
`interactive/grounding.py`'s own grounding is already scoped to "the document currently open," so
the chat is too. History is one in-memory list per `(filename, extension)`, held in a plain dict
closed over by every route (`chat_history`, inside `create_app`) - gone when the session ends,
never written to disk.

**Color-token form (ticket #154, Phase 2's first slice).** Coexists with the raw-text editor on
`tokens.json`'s own edit page, not a replacement for it - `pages.color_token_form` renders `""`
(nothing) when `filename != "tokens"`, so every other document's page is unaffected. Saving reuses
`interactive/token_form.py::save_color_tokens`, which itself reuses `save_customized` - no second
write or validation path for this field kind.

## create_app

One Flask app for one site's interactive session. `out_dir`/`site` (bundled as a `SiteOutput`),
`agent`, and `chat_history` are all closed over by every route rather than read from Flask's own
request-global state - this app is never reused across sites, so there is nothing to gain from
threading them through `request`/`g`. The `chat` route calls `agent.converse()` with the
accumulated history plus a `system_instruction` `interactive/grounding.py::system_instruction_for`
builds fresh every turn; a failure talking to the model (caught broadly - the local model backend
is entirely out of this app's control) pops the unanswered user turn back off the history rather
than leaving a dangling question the model never actually saw. `save_colors` strips each submitted
field's own `token:` prefix and hands the result straight to
`interactive/token_form.py::save_color_tokens`.

## ServerThread

Wraps `werkzeug.serving.make_server()` so the main process (or, once started, a request handler on
the very app it's serving) can call `.shutdown()` on it - see the module's own "Shutdown
mechanism" section for why this specific shape and not `app.run()`.

## run_interactive_server

Blocking entry point `core/interactive_cli.py::run_interactive_command` calls - starts the
server, prints where it's listening, and returns only once "finalizar" (or an external Ctrl+C) has
shut it down. Ctrl+C is caught around `.join()`, not left to propagate raw - it calls the same
`shutdown()` the "finalizar" route does, so both paths tear the server down identically rather
than one being a clean stop and the other an abrupt process kill. `agent` is resolved by the
caller, not this module - it only needs something implementing `Agent.converse()`, never which
backend that is.
