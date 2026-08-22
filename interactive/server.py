"""The interactive dashboard's Flask app factory and server lifecycle
(ticket #151) - a local, single-site editing session over the
documents a normal crawl+docs run already produced. Every page's own
HTML lives in `interactive/pages.py`, not here - this module is
routing and the server's own start/stop, not rendering (split out in
ticket #154 once this file crossed `file-size-audit`'s 300-line WATCH
threshold; see `pages.py`'s own module docstring for why).

**Shutdown mechanism**: `werkzeug.serving.make_server()` run on its own
thread, torn down via that server's own inherited stdlib `.shutdown()`
(ticket #150's own research, `research/150-flask-shutdown-mechanism.md`
on the throwaway `research/flask-shutdown-mechanism` branch) - the
classic `werkzeug.server.shutdown` environ trick was removed in
Werkzeug 2.1, this is the real, current, maintainer-confirmed
replacement. `.shutdown()` must run on a thread other than the one
blocked in `serve_forever()`, so the "finalizar" route spawns a
one-off thread to call it rather than calling it inline.

**Chat** (ticket #153): a panel on the document's own edit page, not a
separate route - grounding (`interactive/grounding.py`) is already
scoped to "the document currently open," so the chat is too. History
is one in-memory list per `(filename, extension)`, closed over by
`create_app` (`chat_history`) - gone when the session ends (map #146's
own "chat history: in-memory only" decision), never written to disk.

**Color-token form** (ticket #154, Phase 2's first slice): coexists
with the raw-text editor on `tokens.json`'s own edit page rather than
replacing it - one `<input type="color">` per `core.color.*` token,
submitting every token's own current value back is a real no-op for
whatever wasn't actually changed (`interactive/token_form.py`'s own
job, not this module's).

Details: docs/dev/interactive/server.md#module
"""
from __future__ import annotations

import threading
from typing import Dict, List, Tuple

import jsonschema
import yaml
from flask import Flask, current_app, redirect, request, url_for
from werkzeug.serving import BaseWSGIServer, make_server

from core.interfaces import Agent

from . import pages
from .customization import DocumentRef, SiteOutput, effective_content, save_customized
from .grounding import grounding_for, system_instruction_for
from .token_form import save_color_tokens


def create_app(out_dir: str, site: str, agent: Agent) -> Flask:
    """One Flask app for one site's interactive session. `where` (an
    `out_dir`/`site` `SiteOutput`), `agent`, and `chat_history` are all
    closed over by every route rather than read from Flask's own
    request-global state - this app is never reused across sites.
    Details: docs/dev/interactive/server.md#create_app
    """
    app = Flask(__name__)
    where = SiteOutput(out_dir=out_dir, site=site)
    # One in-memory conversation per document, gone when the session
    # ends - never written to disk (map #146's own "chat history: in-
    # memory only" decision).
    chat_history: Dict[Tuple[str, str], List[Dict[str, str]]] = {}

    @app.route("/")
    def index():
        return pages.page(f"{site} - Interactive Dashboard", pages.landing_page(where))

    @app.route("/document/<filename>.<extension>", methods=["GET", "POST"])
    def edit_document(filename: str, extension: str):
        ref = DocumentRef(filename=filename, extension=extension)
        error = None
        if request.method == "POST":
            content = request.form["content"]
            try:
                save_customized(where, ref, content)
            except (jsonschema.ValidationError, ValueError, yaml.YAMLError) as exc:
                error = pages.validation_error_message(exc)
            else:
                return redirect(url_for("edit_document", filename=filename, extension=extension))
        else:
            content = effective_content(where, ref)
            if content is None:
                return pages.page("Not found", f"<p>No document named {filename}.{extension} for {site}.</p>"), 404
        history = chat_history.get((filename, extension), [])
        color_form = pages.color_token_form(where) if filename == "tokens" else ""
        body = color_form + pages.document_page(ref, content, error) + pages.chat_panel(ref, history, None)
        return pages.page(f"{filename}.{extension} - {site}", body)

    @app.route("/document/tokens.json/colors", methods=["POST"])
    def save_colors():
        new_values = {
            key[len(pages.COLOR_FIELD_PREFIX):]: value
            for key, value in request.form.items()
            if key.startswith(pages.COLOR_FIELD_PREFIX)
        }
        save_color_tokens(where, new_values)
        return redirect(url_for("edit_document", filename="tokens", extension="json"))

    @app.route("/document/<filename>.<extension>/chat", methods=["POST"])
    def chat(filename: str, extension: str):
        ref = DocumentRef(filename=filename, extension=extension)
        history = chat_history.setdefault((filename, extension), [])
        history.append({"role": "user", "content": request.form["message"]})

        chat_error = None
        try:
            facts = grounding_for(where, ref)
            reply = agent.converse(history, system_instruction=system_instruction_for(ref, facts))
        except Exception as exc:  # the local model backend is out of this app's control
            chat_error = f"Could not reach the model: {exc}"
            history.pop()  # the unanswered user turn doesn't count as part of the conversation
        else:
            history.append({"role": "assistant", "content": reply})

        content = effective_content(where, ref) or ""
        body = pages.document_page(ref, content, None) + pages.chat_panel(ref, history, chat_error)
        return pages.page(f"{filename}.{extension} - {site}", body)

    @app.route("/finalizar", methods=["POST"])
    def finalizar():
        server_thread: "ServerThread" = current_app.config["SERVER_THREAD"]
        threading.Thread(target=server_thread.shutdown).start()
        return pages.page("Finalizado", "<h1>Sesión finalizada.</h1><p>Podés cerrar esta pestaña.</p>")

    return app


class ServerThread(threading.Thread):
    """Runs `app` on a real `werkzeug.serving.make_server()` instance in
    its own thread, so the main process can keep going (and a route on
    `app` itself can trigger `shutdown()`) - see module docstring for
    why this specific shape.
    Details: docs/dev/interactive/server.md#serverthread
    """

    def __init__(self, app: Flask, host: str = "127.0.0.1", port: int = 5050) -> None:
        super().__init__()
        self.server: BaseWSGIServer = make_server(host, port, app, threaded=True)
        self.host = host
        self.port = port

    def run(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()


def run_interactive_server(
    out_dir: str, site: str, agent: Agent, host: str = "127.0.0.1", port: int = 5050
) -> None:
    """Blocking entry point: start the server, print where it's
    listening, and return only once the "finalizar" route (or an
    external Ctrl+C) has shut it down. `agent` is resolved by the
    caller (`core/interactive_cli.py`, the same `PragmaConfig.agent` +
    `AGENT_REGISTRY` pattern `docs_cli.py`/`crawl_cli.py` already use) -
    this module doesn't know or care which backend it is, only that it
    implements `Agent.converse()`.
    Details: docs/dev/interactive/server.md#run_interactive_server
    """
    app = create_app(out_dir, site, agent)
    server_thread = ServerThread(app, host=host, port=port)
    app.config["SERVER_THREAD"] = server_thread

    server_thread.start()
    print(f"Interactive dashboard for {site} running at http://{host}:{port}/ - Ctrl+C or the "
          "in-page \"Finalizar\" button to stop.")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        server_thread.shutdown()
        server_thread.join()
