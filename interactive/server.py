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

**In-flight requests drain before the server actually closes** (ticket
#157). `.shutdown()` alone only stops the accept loop - it never waits
for a request already being handled on its own `ThreadingMixIn` worker
thread, and `serve_forever()` never calls `server_close()` on its own
either, so without this, an in-flight save or chat reply was just
abandoned. `ServerThread.shutdown()` now calls `server_close()` right
after `.shutdown()` returns - `ThreadedWSGIServer`'s own inherited
`block_on_close = True` makes that join every still-running request
thread before returning. Both "finalizar" and an external Ctrl+C go
through this same `ServerThread.shutdown()`, so neither gets special
"kill it now" treatment. No separate timeout was added for the drain
itself - `LocalAgent`'s own 300s request timeout is the only bound, and
adding a second one would be solving a problem (a hung chat call
in-flight at the exact moment of shutdown) nobody has actually hit.

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

**Diff/error gutter** (ticket #155): every `edit_document` render now
fetches both `effective_content` (or the submitted form content on a
failed POST) and `original_content` (the crawl's own output,
regardless of any customized copy), bundled into a
`pages.DocumentEditState` - `interactive/pages.py::document_page` owns
the actual diff/gutter rendering, this module only gathers the two
strings.

**Generic form** (ADR-0034, ticket #158): `requirements.json` gets a
schema-driven review panel alongside the raw-text editor, the same
coexistence `pages.color_token_form` already established for
`tokens.json` (`browser-support-matrix.json` was this ticket's other
originally-planned case, but its own generator never actually produces
it - see `interactive/generic_form.py`'s own module docstring).
`save_fields` parses each submitted `entry:<index>:<field>` key
(`interactive/generic_form.py::ENTRY_FIELD_PREFIX`) into a per-row
update dict and hands it to `generic_form.save_generic_form` - this
module still only parses form data, `interactive/generic_form.py` still
owns knowing what a field's real widget/value is.

**View/edit split** (ticket #178): every document opens in a read-only
view (`view_document`, GET `/document/<filename>.<extension>`) that
shows the same rendered output the static dashboard already gives.
`edit_document` (GET/POST `/document/<filename>.<extension>/edit`)
is the diff-gutter editor, only reachable via the "Edit" link on the
view page. A successful save redirects back to the view page, not the
editor - the reviewer returns to the rendered result, not to the raw
diff, after each save. `dashboard.renderer_audit.renderer_for` drives
the view dispatch, so the interactive and static dashboards stay in
sync automatically.

Details: docs/dev/interactive/server.md#module
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import jsonschema
import yaml
from flask import Flask, current_app, redirect, request, url_for, jsonify, send_from_directory
from werkzeug.serving import BaseWSGIServer, make_server

from dashboard.renderer_audit import renderer_for

from core.interfaces import Agent
from core.config import PragmaConfig

def validation_error_message(exc: Exception) -> str:
    if isinstance(exc, jsonschema.ValidationError):
        return f"Schema validation failed at {list(exc.absolute_path) or '(root)'}: {exc.message}"
    return f"Could not parse this document: {exc}"


def simple_html_page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
        '<style>body { background: #0f1115; color: #e4e7ee; font-family: sans-serif; padding: 40px; text-align: center; }</style>'
        f'</head><body>{body}</body></html>\n'
    )
from .customization import DocumentRef, SiteOutput, customized_path, effective_content, original_content, save_customized, available_documents, schema_path_for
from .generic_form import ENTRY_FIELD_PREFIX, save_generic_form
from .grounding import (
    grounding_for,
    system_instruction_for,
    select_grounding_documents,
    grounding_for_documents,
    system_instruction_for_global,
)
from .token_form import save_color_tokens


def _parse_entry_updates(form: Dict[str, str]) -> Dict[int, Dict[str, str]]:
    """`{"entry:2:hitl_status": "approved", ...}` ->
    `{2: {"hitl_status": "approved"}, ...}` - the inverse of
    `interactive/pages.py::_generic_field_html`'s own field naming.
    """
    updates: Dict[int, Dict[str, str]] = {}
    for key, value in form.items():
        if not key.startswith(ENTRY_FIELD_PREFIX):
            continue
        _, index, field_name = key.split(":", 2)
        updates.setdefault(int(index), {})[field_name] = value
    return updates


def create_app(out_dir: str, site: Optional[str], agent: Agent, db_dir: Optional[str] = None) -> Flask:
    """One Flask app for the interactive session. Dynamic stores are
    resolved per site slug, and the app serves the static explorer SPA
    and a clean REST API.
    Details: docs/dev/interactive/server.md#create_app
    """
    app = Flask(__name__)
    explorer_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../tools/graph-explorer/dist"))

    # Resolve Kùzu database directory from configuration if not explicitly provided
    if db_dir is None:
        config = PragmaConfig.load()
        ladybug_opts = config.graph_stores.get("ladybug", {})
        db_dir = ladybug_opts.get("directory", "data/sites")
        if not os.path.isdir(db_dir) or not list(Path(db_dir).glob("*.lbdb")):
            if os.path.isdir(out_dir):
                db_dir = out_dir

    # Cache for LadybugGraphStore instances
    _stores = {}

    def get_store_for_site(site_slug: str):
        if not site_slug:
            raise ValueError("No site slug provided")
        if site_slug not in _stores:
            from database.ladybug.store import LadybugGraphStore
            _stores[site_slug] = LadybugGraphStore(site=site_slug, directory=db_dir)
        return _stores[site_slug]

    def get_available_sites() -> List[str]:
        # Glob *.lbdb under db_dir
        return sorted([path.stem for path in Path(db_dir).glob("*.lbdb")])

    @app.route("/")
    def index():
        return redirect("/index.html")

    @app.route("/api/sites")
    def api_sites():
        return jsonify(get_available_sites())

    @app.route("/api/<site>/graph")
    def api_site_graph(site):
        from core.documents import DocumentRequest
        from generators.graph_export import build_export_graph
        try:
            site_store = get_store_for_site(site)
            site_store.connect()
            doc_request = DocumentRequest(
                graph_store=site_store,
                site=site,
                agent=agent,
                settings={"target": site},
            )
            graph_data = build_export_graph(doc_request)
            return jsonify(graph_data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/<site>/documents")
    def api_documents(site):
        site_where = SiteOutput(out_dir=out_dir, site=site)
        docs = []
        for ref in available_documents(site_where):
            docs.append({
                "filename": ref.filename,
                "extension": ref.extension,
                "customized": os.path.exists(customized_path(site_where, ref)),
                "has_schema": bool(schema_path_for(ref.filename))
            })
        return jsonify(docs)

    @app.route("/api/<site>/documents/<filename>.<extension>")
    def api_document_detail(site, filename, extension):
        ref = DocumentRef(filename=filename, extension=extension)
        site_where = SiteOutput(out_dir=out_dir, site=site)
        
        orig = original_content(site_where, ref)
        eff = effective_content(site_where, ref)
        
        if orig is None and eff is None:
            return jsonify({"error": f"Document {filename}.{extension} not found"}), 404
            
        renderer = renderer_for(f"{ref.filename}.{ref.extension}")
        return jsonify({
            "filename": ref.filename,
            "extension": ref.extension,
            "content": eff,
            "original": orig,
            "customized": os.path.exists(customized_path(site_where, ref)),
            "has_schema": bool(schema_path_for(ref.filename)),
            "renderer": renderer
        })

    @app.route("/api/<site>/documents/<filename>.<extension>", methods=["POST"])
    def api_save_document(site, filename, extension):
        ref = DocumentRef(filename=filename, extension=extension)
        site_where = SiteOutput(out_dir=out_dir, site=site)
        
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"success": False, "error": "Missing content"}), 400
            
        content = data["content"]
        
        # Schema validation if applicable
        schema_path = schema_path_for(ref.filename)
        if schema_path:
            import json
            import jsonschema
            try:
                parsed = json.loads(content)
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                jsonschema.validate(instance=parsed, schema=schema)
            except Exception as exc:
                error_msg = validation_error_message(exc)
                error_path = list(exc.absolute_path) if isinstance(exc, jsonschema.ValidationError) else []
                return jsonify({
                    "success": False,
                    "error": error_msg,
                    "error_path": error_path
                }), 400
                
        try:
            save_customized(site_where, ref, content)
            return jsonify({"success": True})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/<site>/tokens/colors", methods=["POST"])
    def api_save_colors(site):
        site_where = SiteOutput(out_dir=out_dir, site=site)
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Missing JSON body"}), 400
        try:
            save_color_tokens(site_where, data)
            return jsonify({"success": True})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/<site>/documents/<filename>.<extension>/fields", methods=["POST"])
    def api_save_fields(site, filename, extension):
        ref = DocumentRef(filename=filename, extension=extension)
        site_where = SiteOutput(out_dir=out_dir, site=site)
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Missing JSON body"}), 400
        try:
            updates = _parse_entry_updates(data)
            save_generic_form(site_where, ref, updates)
            return jsonify({"success": True})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/<site>/chat", methods=["POST"])
    def api_chat(site):
        site_where = SiteOutput(out_dir=out_dir, site=site)
        data = request.get_json()
        if not data or "message" not in data or "history" not in data:
            return jsonify({"success": False, "error": "Missing parameters"}), 400
            
        message = data["message"]
        history = list(data["history"])
        context = data.get("context")
        
        # Append the new user turn
        history.append({"role": "user", "content": message})
        
        try:
            if context and "filename" in context and "extension" in context:
                ref = DocumentRef(filename=context["filename"], extension=context["extension"])
                facts = grounding_for(site_where, ref)
                sys_instruction = system_instruction_for(ref, facts)
            else:
                selected_refs = select_grounding_documents(site_where, message)
                sourced_facts = grounding_for_documents(site_where, selected_refs)
                sys_instruction = system_instruction_for_global(selected_refs, sourced_facts)
                
            reply = agent.converse(history, system_instruction=sys_instruction)
            return jsonify({"success": True, "reply": reply})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/finalizar", methods=["POST"])
    def finalizar():
        server_thread: "ServerThread" = current_app.config["SERVER_THREAD"]
        threading.Thread(target=server_thread.shutdown).start()
        return simple_html_page("Finalizado", "<h1>Sesión finalizada.</h1><p>Podés cerrar esta pestaña.</p>")

    @app.route("/graph")
    def serve_graph_redirect():
        return redirect("/index.html")

    @app.route("/index.html")
    def serve_graph_index():
        return send_from_directory(explorer_dist, "index.html")

    @app.route("/lists.html")
    def serve_graph_lists():
        return send_from_directory(explorer_dist, "lists.html")

    @app.route("/assets/<path:filename>")
    def serve_graph_assets(filename):
        return send_from_directory(os.path.join(explorer_dist, "assets"), filename)

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
        # ThreadedWSGIServer.daemon_threads defaults True - socketserver's
        # own _Threads.append() explicitly skips tracking any daemon
        # thread, which makes server_close()'s in-flight-request join a
        # silent no-op otherwise (confirmed: measured 0.51s vs a genuine
        # 2.00s wait for a real in-flight request, same code, only this
        # flag differing). False is what makes the join in run() real.
        self.server.daemon_threads = False
        self.host = host
        self.port = port

    def run(self) -> None:
        self.server.serve_forever()
        self.server.server_close()

    def shutdown(self) -> None:
        self.server.shutdown()


def run_interactive_server(
    out_dir: str, site: Optional[str], agent: Agent, host: str = "127.0.0.1", port: int = 5050
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
    site_desc = f"site {site}" if site else "all crawled sites"
    print(f"Interactive dashboard for {site_desc} running at http://{host}:{port}/ - Ctrl+C or the "
          "in-page \"Finalizar\" button to stop.")
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server_thread.shutdown()
        server_thread.join()
