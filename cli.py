#!/usr/bin/env python3
"""
Command-line interface for Pragma.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from dotenv import load_dotenv

# Path setup to allow running from any cwd (cli.py lives at the project root)
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from core import bootstrap  # noqa: F401  -- populates the plugin registries
from core import prompts
from core.app import run_app
from core.cli_shared import apply_budget_flags
from core.cluster_cli import run_cluster_command
from core.config import PragmaConfig
from core.crawl_cli import run_crawl_command
from core.docs_cli import run_docs_command
from core.dynamic_cli import run_dynamic_command
from core.engine import Engine, EngineRunResult
from core.interactive_cli import run_interactive_command
from core.login_cli import run_login_command
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY
from core.static_cli import run_static_command
from core.wizard import run_config_wizard


def _print_documents(result: EngineRunResult) -> None:
    """List every document the run wrote, master document first.

    It goes first because it is the one to open: it indexes the others and
    carries the coverage numbers. Buried in the middle of an alphabetical
    list it is just another filename, which is exactly the "which of these
    do I open" problem it exists to solve.

    Iterates `result.documents` rather than printing a line per named
    field, so a document added in a later phase shows up here without this
    function changing - the same reason `Engine` stopped hardcoding one
    block per output file.
    Details: docs/dev/cli.md#_print_documents
    """
    if not result.documents:
        print("No documents were generated - see the errors above.")
        return

    master = next((d for d in result.documents if d.name == "master"), None)
    if master:
        print(f"\nStart here -> {master.path}")
    width = max(len(d.title) for d in result.documents)
    for document in result.documents:
        if document is master:
            continue
        print(f"  {document.title:<{width}}  {document.path}")
    print()


def parse_args(argv: list) -> argparse.Namespace:
    """Parse command line arguments for a run (analysis) invocation."""
    parser = argparse.ArgumentParser(
        description="Pragma: Autonomous Web-App Archaeology",
        epilog="Run `python3 cli.py config` once to set up your provider/model/api key.",
    )
    parser.add_argument("url", nargs="?", help="URL to explore")
    parser.add_argument("--url", "-u", dest="url_flag", help="URL to explore (same as positional)")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--agent",
        "--provider",
        "-p",
        dest="agent",
        help=f"Agent plugin ({', '.join(AGENT_REGISTRY.names())})",
    )
    parser.add_argument(
        "--graph-store",
        dest="graph_store",
        help=f"Graph store plugin ({', '.join(GRAPH_STORE_REGISTRY.names())})",
    )
    parser.add_argument("--out", "-o", dest="out_dir", help="Output folder for PRDs")
    parser.add_argument(
        "--debug-logs-dir",
        dest="debug_logs_dir",
        help="Folder for per-run debug artifacts: every crawl4ai hook firing, plus each page's "
        "markdown conversion (default: data/debug_logs). Pass an empty string to disable.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        dest="wait_seconds",
        help="Seconds to let a page settle before discovery reads it (default: 2). Raise this for "
        "JS-heavy sites (React/Vue SPAs) where components/links can otherwise read as 0 - the page's "
        "pre-hydration HTML shell satisfies the default wait condition before real content renders.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        dest="max_pages",
        help="Total pages to visit before stopping the crawl (default: unbounded - crawl until the "
        "URL frontier is exhausted).",
    )
    parser.add_argument(
        "--page-concurrency",
        type=int,
        dest="page_concurrency",
        help="How many pages to visit at once (default: 4) - the single biggest lever for a large "
        "crawl's wall-clock time, since each page pays its own settle-wait/interaction cost. Paired "
        "with a memory ceiling (MechanicalCrawlerConfig.memory_ceiling_percent, not yet exposed here) "
        "that pauses picking up new pages under memory pressure, so raising this further trades CPU/"
        "RAM for speed rather than risking an out-of-memory crash outright.",
    )
    parser.add_argument(
        "--max-pages-per-run",
        type=int,
        dest="budget_pages",
        help="Stop this run after N pages and leave the rest Pending for the next one, which "
        "picks up where this stopped (default: whatever crawl_budget.pages says in the YAML, "
        "or no limit). Use it to walk a large site in short, inspectable passes instead of one "
        "long opaque crawl.",
    )
    parser.add_argument(
        "--max-minutes-per-run",
        type=float,
        dest="budget_minutes",
        help="Stop this run after N minutes. Worth setting even when --max-pages-per-run is what "
        "you actually want: a page whose DOM keeps producing new components finishes no page at "
        "all, so a page-only budget never trips and the run goes forever.",
    )
    parser.add_argument(
        "--full",
        dest="full_run",
        action="store_true",
        default=None,
        help="Ignore every configured budget and crawl until the frontier drains - the overnight "
        "run. Not a separate mode: it clears the budgets and takes the same code path.",
    )
    parser.add_argument("--headed", action="store_true", help="Run browser with visible UI")
    parser.add_argument(
        "--tree-ascii",
        dest="tree_ascii",
        action="store_true",
        default=None,
        help="Render the component-tree document with plain ASCII (|--, `--) instead of the "
        "default Unicode box-drawing characters (├──, └──) - for terminals that mangle Unicode.",
    )
    parser.add_argument(
        "--debug-logs-keep-last",
        type=int,
        dest="debug_logs_keep_last",
        help="Keep only the N most recent data/debug_logs/ run directories for this site+URL, deleting "
        "older ones once a run finishes (default: unbounded - keep every run forever).",
    )
    parser.add_argument(
        "--export-json",
        dest="export_json",
        action="store_true",
        default=None,
        help="Also write data/output/{slug}_graph_{timestamp}.json - the full crawl graph (pages, edges, "
        "component ledger, text content) as structured JSON, alongside the prose PRD and the "
        "component tree - for a downstream tool that wants the crawl's facts as data.",
    )
    parser.add_argument(
        "--fresh",
        dest="fresh",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Purge this site's previously recorded graph_store state before crawling "
        "(default: off; matters for --graph-store ladybug, which persists across runs). "
        "Leave it off to resume a previous run: the pages it left Pending are the saved "
        "progress the next run picks up. Pass --fresh when the site itself changed and "
        "the recorded facts are stale.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Bare invocation launches the menu app; `config` jumps to the wizard;
    `login` captures a session; `static` runs a content-capture crawl;
    `cluster` groups an already-crawled site's components into families;
    `dynamic` interacts with a site's frontier, resuming from `static`/
    `cluster` output when there is any; `docs` generates documents from an
    existing site DB with no crawl; `interactive` serves an already-documented
    site's own output as an editable local dashboard, no crawl or graph store
    connection either; `crawl` chains static -> cluster -> dynamic (never
    `docs`/`interactive` - both stay separate, explicit invocations); flags
    run the full crawl+analysis pipeline directly.
    Details: docs/dev/cli.md#main
    """
    argv = sys.argv[1:]
    if argv and argv[0] == "config":
        run_config_wizard()
        return
    if argv and argv[0] == "login":
        run_login_command(argv[1:])
        return
    if argv and argv[0] == "static":
        run_static_command(argv[1:])
        return
    if argv and argv[0] == "cluster":
        run_cluster_command(argv[1:])
        return
    if argv and argv[0] == "dynamic":
        run_dynamic_command(argv[1:])
        return
    if argv and argv[0] == "docs":
        run_docs_command(argv[1:])
        return
    if argv and argv[0] == "interactive":
        run_interactive_command(argv[1:])
        return
    if argv and argv[0] == "crawl":
        run_crawl_command(argv[1:])
        return

    if not argv:
        if sys.stdin.isatty():
            run_app()
            return
        print("Error: URL must be provided (positional arg, --url, YAML config, or URL env var)")
        sys.exit(2)

    args = parse_args(argv)
    url = args.url_flag or args.url
    overrides = {
        k: v
        for k, v in vars(args).items()
        if k not in ("url", "url_flag", "config_path", "budget_pages", "budget_minutes", "full_run")
    }
    if overrides.pop("headed", False):
        overrides["headless"] = False
    overrides["url"] = url

    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)
    apply_budget_flags(config, args)

    if not config.url:
        if sys.stdin.isatty():
            config.url = prompts.text("URL to analyze")
        if not config.url:
            print(
                "Error: URL must be provided (positional arg, --url, YAML config, or URL env var)"
            )
            sys.exit(2)

    try:
        print(f"Starting autonomous archaeology for: {config.url}")
        print(f"Wiring: agent={config.agent} graph_store={config.graph_store}")
        engine = Engine.from_config(config)
        result = engine.run(config.url)
        _print_documents(result)
        print(f"Run recorded in manifest: {result.manifest_path}")
        print(f"Run index updated: {result.index_path}")

    except Exception as exc:
        print(f"Critical error during exploration: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
