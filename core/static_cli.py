"""`pragma static` command: parse its args, run the scout-only crawl,
report the result. Details: docs/dev/core/static_cli.md#module
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from .cli_shared import apply_budget_flags
from .config import PragmaConfig
from .registry import GRAPH_STORE_REGISTRY
from .static_engine import StaticEngine, StaticRunResult


def parse_static_args(argv: list) -> argparse.Namespace:
    """A content-capture crawl, not the full run: no agent, no output
    documents, so it takes only the flags that still mean something
    without either of those.
    Details: docs/dev/core/static_cli.md#parse_static_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py static",
        description="Scout-only, prefetch=true crawl: captures HTML/CSS/routes into the graph "
        "store without clicking or filling anything.",
    )
    parser.add_argument("url", help="URL to crawl")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--graph-store",
        dest="graph_store",
        help=f"Graph store plugin ({', '.join(GRAPH_STORE_REGISTRY.names())})",
    )
    parser.add_argument("--max-pages", type=int, dest="max_pages", help="Total pages to visit before stopping")
    parser.add_argument(
        "--page-concurrency", type=int, dest="page_concurrency", help="How many pages to visit at once"
    )
    parser.add_argument(
        "--max-pages-per-run", type=int, dest="budget_pages",
        help="Stop this run after N pages, leaving the rest Pending for the next one",
    )
    parser.add_argument(
        "--max-minutes-per-run", type=float, dest="budget_minutes", help="Stop this run after N minutes",
    )
    parser.add_argument(
        "--full", dest="full_run", action="store_true", default=None,
        help="Ignore every configured budget and crawl until the frontier drains",
    )
    parser.add_argument("--headed", action="store_true", help="Run browser with visible UI")
    parser.add_argument(
        "--login", dest="login_enabled", action=argparse.BooleanOptionalAction, default=None,
        help="Auto-detect a login form and open a headed browser for sign-in before crawling "
        "(default: on). Pass --no-login to always crawl anonymously.",
    )
    parser.add_argument(
        "--fresh", dest="fresh", action=argparse.BooleanOptionalAction, default=None,
        help="Purge this site's previously recorded graph_store state before crawling",
    )
    return parser.parse_args(argv)


def run_static_command(argv: list) -> None:
    """`pragma static <url>`: crawl, don't analyze - see `StaticEngine` for
    what that means in practice. Details: docs/dev/core/static_cli.md#run_static_command
    """
    args = parse_static_args(argv)
    overrides = {
        k: v
        for k, v in vars(args).items()
        if k not in ("url", "config_path", "budget_pages", "budget_minutes", "full_run")
    }
    if overrides.pop("headed", False):
        overrides["headless"] = False
    overrides["url"] = args.url

    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)
    apply_budget_flags(config, args)

    try:
        print(f"Starting static capture for: {config.url}")
        print(f"Wiring: graph_store={config.graph_store}")
        engine = StaticEngine.from_config(config)
        result: StaticRunResult = asyncio.run(engine.run(config.url))
        print(f"\nScouted {result.pages_scouted}/{result.pages_total} page(s) for {result.site}.")
        if result.login_session_path:
            print(f"Login session used: {result.login_session_path}")
    except Exception as exc:
        print(f"Critical error during static capture: {exc}")
        sys.exit(1)
