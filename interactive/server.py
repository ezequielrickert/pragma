"""The interactive dashboard's Flask server (ticket #151) - a local,
single-site editing session over the documents a normal crawl+docs run
already produced. Plain Python string building for every page, no
Jinja templates: the same convention `dashboard/generic_template.py`
already uses, not a second one.

**Shutdown mechanism**: `werkzeug.serving.make_server()` run on its own
thread, torn down via that server's own inherited stdlib `.shutdown()`
(ticket #150's own research, `research/150-flask-shutdown-mechanism.md`
on the throwaway `research/flask-shutdown-mechanism` branch) - the
classic `werkzeug.server.shutdown` environ trick was removed in
Werkzeug 2.1, this is the real, current, maintainer-confirmed
replacement. `.shutdown()` must run on a thread other than the one
blocked in `serve_forever()`, so the "finalizar" route spawns a
one-off thread to call it rather than calling it inline.

Details: docs/dev/interactive/server.md#module
"""
from __future__ import annotations

import threading
from html import escape
from typing import Optional

import jsonschema
import yaml
from flask import Flask, current_app, redirect, request, url_for
from werkzeug.serving import BaseWSGIServer, make_server

from .customization import DocumentRef, SiteOutput, available_documents, effective_content, save_customized, schema_path_for

_STYLE = """
:root {
  --bg: #0f1115; --panel: #161922; --border: #2a2f3a;
  --text: #e4e7ee; --text-dim: #8b93a7; --accent: #5b8cff; --danger: #f87171;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
main { max-width: 900px; margin: 0 auto; padding: 32px; }
a { color: var(--accent); text-decoration: none; }
h1 { font-size: 20px; }
ul.documents { list-style: none; padding: 0; }
ul.documents li { padding: 6px 0; border-bottom: 1px solid var(--border); }
textarea { width: 100%; min-height: 400px; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; }
.error { background: #3a1e1e; border: 1px solid var(--danger); color: var(--danger);
  padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; white-space: pre-wrap; }
button { background: var(--accent); color: white; border: none; border-radius: 6px;
  padding: 8px 18px; font-size: 14px; cursor: pointer; }
.finalizar { background: var(--danger); }
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{_STYLE}</style></head><body><main>{body}</main></body></html>\n"
    )


def _landing_page(where: SiteOutput) -> str:
    items = "".join(
        f'<li><a href="{url_for("edit_document", filename=ref.filename, extension=ref.extension)}">'
        f"{escape(ref.filename)}.{escape(ref.extension)}</a></li>"
        for ref in available_documents(where)
    )
    return (
        f"<h1>{escape(where.site)}</h1>"
        '<p>Every document this crawl produced, editable below. Editing writes a customized '
        "copy - the original crawl output is never touched.</p>"
        f'<ul class="documents">{items}</ul>'
        '<form method="post" action="/finalizar" onsubmit="return confirm(\'Finalizar sesión?\')">'
        '<button class="finalizar" type="submit">Finalizar</button></form>'
    )


def _validation_error_message(exc: Exception) -> str:
    if isinstance(exc, jsonschema.ValidationError):
        return f"Schema validation failed at {list(exc.absolute_path) or '(root)'}: {exc.message}"
    return f"Could not parse this document: {exc}"


def _document_page(ref: DocumentRef, content: str, error: Optional[str]) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    schema_note = (
        f"Validated against {escape(schema_path_for(ref.filename))} on save."
        if schema_path_for(ref.filename)
        else "No schema known for this document - saved as-is, unvalidated."
    )
    return (
        f'<p><a href="{url_for("index")}">&larr; {escape(ref.filename)}.{escape(ref.extension)}</a></p>'
        f"<h1>{escape(ref.filename)}.{escape(ref.extension)}</h1>"
        f"<p>{schema_note}</p>"
        f"{error_html}"
        '<form method="post">'
        f"<textarea name=\"content\">{escape(content)}</textarea><br><br>"
        '<button type="submit">Save</button>'
        "</form>"
    )


def create_app(out_dir: str, site: str) -> Flask:
    """One Flask app for one site's interactive session. `where` (an
    `out_dir`/`site` `SiteOutput`) is closed over by every route rather
    than read from Flask's own request-global state - this app is never
    reused across sites.
    Details: docs/dev/interactive/server.md#create_app
    """
    app = Flask(__name__)
    where = SiteOutput(out_dir=out_dir, site=site)

    @app.route("/")
    def index():
        return _page(f"{site} - Interactive Dashboard", _landing_page(where))

    @app.route("/document/<filename>.<extension>", methods=["GET", "POST"])
    def edit_document(filename: str, extension: str):
        ref = DocumentRef(filename=filename, extension=extension)
        error = None
        if request.method == "POST":
            content = request.form["content"]
            try:
                save_customized(where, ref, content)
            except (jsonschema.ValidationError, ValueError, yaml.YAMLError) as exc:
                error = _validation_error_message(exc)
            else:
                return redirect(url_for("edit_document", filename=filename, extension=extension))
        else:
            content = effective_content(where, ref)
            if content is None:
                return _page("Not found", f"<p>No document named {escape(filename)}.{escape(extension)} for {escape(site)}.</p>"), 404
        return _page(f"{filename}.{extension} - {site}", _document_page(ref, content, error))

    @app.route("/finalizar", methods=["POST"])
    def finalizar():
        server_thread: "ServerThread" = current_app.config["SERVER_THREAD"]
        threading.Thread(target=server_thread.shutdown).start()
        return _page("Finalizado", "<h1>Sesión finalizada.</h1><p>Podés cerrar esta pestaña.</p>")

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


def run_interactive_server(out_dir: str, site: str, host: str = "127.0.0.1", port: int = 5050) -> None:
    """Blocking entry point: start the server, print where it's
    listening, and return only once the "finalizar" route (or an
    external Ctrl+C) has shut it down.
    Details: docs/dev/interactive/server.md#run_interactive_server
    """
    app = create_app(out_dir, site)
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
