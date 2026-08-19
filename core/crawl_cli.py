"""`pragma crawl` command: parse its args, chain static -> cluster ->
dynamic, report the result.
Details: docs/dev/core/crawl_cli.md#module
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from .cli_shared import apply_budget_flags
from .config import PragmaConfig
from .crawl_engine import CrawlEngine, CrawlRunResult
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def parse_crawl_args(argv: list) -> argparse.Namespace:
    """A superset of `static`'s own flags - `cluster`/`dynamic` take no
    flags `static` doesn't already cover (`dynamic` reuses the same
    login/budget knobs; `cluster` takes none at all).
    Details: docs/dev/core/crawl_cli.md#parse_crawl_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py crawl",
        description="Chain static -> cluster -> dynamic against one URL, stopping at whichever "
        "phase fails first. Never runs `pragma docs` - that stays a fully separate, explicit "
        "invocation.",
    )
    parser.add_argument("url", help="URL to crawl")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--agent", "--provider", "-p", dest="agent",
        help=f"Agent plugin ({', '.join(AGENT_REGISTRY.names())})",
    )
    parser.add_argument(
        "--graph-store", dest="graph_store",
        help=f"Graph store plugin ({', '.join(GRAPH_STORE_REGISTRY.names())})",
    )
    parser.add_argument("--max-pages", type=int, dest="max_pages", help="Total pages to visit before stopping")
    parser.add_argument(
        "--page-concurrency", type=int, dest="page_concurrency", help="How many pages to visit at once"
    )
    parser.add_argument(
        "--max-pages-per-run", type=int, dest="budget_pages",
        help="Stop each crawling phase after N pages, leaving the rest Pending for the next one",
    )
    parser.add_argument(
        "--max-minutes-per-run", type=float, dest="budget_minutes",
        help="Stop each crawling phase after N minutes",
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
        help="Purge this site's previously recorded graph_store state before the static phase",
    )
    parser.add_argument(
        "--mode", dest="mode", choices=["stateful", "immutable"],
        help="'stateful' (default) sends every request unchanged. 'immutable' still clicks/fills "
        "every component but blocks POST/PUT/PATCH/DELETE (and mutation-heuristic GETs) before "
        "they reach the server - for a sensitive site where no real operation should happen. "
        "Reaches the dynamic phase unchanged; static/cluster ignore it.",
    )
    return parser.parse_args(argv)


def run_crawl_command(argv: list) -> None:
    """`pragma crawl <url>`: static -> cluster -> dynamic - see
    `CrawlEngine` for what that means in practice.
    Details: docs/dev/core/crawl_cli.md#run_crawl_command
    """
    args = parse_crawl_args(argv)
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
        print(f"Starting pragma crawl for: {config.url}")
        print(f"Wiring: agent={config.agent} graph_store={config.graph_store}")
        engine = CrawlEngine.from_config(config)
        result: CrawlRunResult = asyncio.run(engine.run(config.url))
    except Exception as exc:
        # A failure inside one of the three phases is caught by
        # CrawlEngine.run() itself and reported via result.failed_phase
        # below - reaching here means something broke outside all three
        # (config/wiring), not a phase this command can name.
        print(f"Critical error before any phase could run: {exc}")
        sys.exit(1)

    if result.succeeded:
        print(f"\npragma crawl finished all three phases for {result.site}.")
    else:
        print(
            f"\npragma crawl stopped at the {result.failed_phase!r} phase "
            f"for {result.site}: {result.error}"
        )
        sys.exit(1)
