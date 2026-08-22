"""`pragma dynamic` command: parse its args, run the resume-aware
interaction pass, report the result.
Details: docs/dev/core/dynamic_cli.md#module
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from .cli_shared import apply_budget_flags
from .config import PragmaConfig
from .dynamic_engine import DynamicEngine, DynamicRunResult
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def parse_dynamic_args(argv: list) -> argparse.Namespace:
    """A URL, not a bare site: unlike `pragma cluster`, `pragma dynamic`
    still has to know where to start a fused crawl when there is nothing
    to resume - see `DynamicEngine.run`'s fallback.
    Details: docs/dev/core/dynamic_cli.md#parse_dynamic_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py dynamic",
        description="Interact with a site's frontier: resumes from a prior `pragma static` run "
        "when one exists, sampling only a few instances per component family known from "
        "`pragma cluster` instead of clicking/filling every one; falls back to independent "
        "full discovery+interaction when there's nothing to resume.",
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
        "--mode", dest="mode", choices=["stateful", "immutable"],
        help="'stateful' (default) sends every request unchanged. 'immutable' still clicks/fills "
        "every component but blocks POST/PUT/PATCH/DELETE (and mutation-heuristic GETs) before "
        "they reach the server - for a sensitive site where no real operation should happen.",
    )
    return parser.parse_args(argv)


def run_dynamic_command(argv: list) -> None:
    """`pragma dynamic <url>`: interact, don't scout or analyze - see
    `DynamicEngine` for what that means in practice.
    Details: docs/dev/core/dynamic_cli.md#run_dynamic_command
    """
    args = parse_dynamic_args(argv)
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
        print(f"Starting dynamic interaction for: {config.url}")
        print(f"Wiring: agent={config.agent} graph_store={config.graph_store}")
        engine = DynamicEngine.from_config(config)
        result: DynamicRunResult = asyncio.run(engine.run(config.url))
        mode = "resumed from static" if result.resumed_from_static else "independent full discovery"
        print(
            f"\nDynamic run ({mode}) finished: "
            f"{result.pages_finished}/{result.pages_total} page(s) for {result.site}."
        )
        if result.families_sampled:
            noun = "family" if result.families_sampled == 1 else "families"
            print(
                f"Sampled {result.families_sampled} known component {noun}, "
                f"skipped {result.instances_skipped} already-sampled instance(s)."
            )
        if result.exact_reuse_skipped:
            print(
                f"Skipped {result.exact_reuse_skipped} exact-tier reuse instance(s) "
                "already interacted with elsewhere."
            )
    except Exception as exc:
        print(f"Critical error during dynamic interaction: {exc}")
        sys.exit(1)
