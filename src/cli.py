"""
Command-line interface for Pragma.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from dotenv import load_dotenv

# Path setup to allow running from project root
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from src.core import bootstrap  # noqa: F401  -- populates the plugin registries
from src.core import prompts
from src.core.app import run_app
from src.core.config import PragmaConfig
from src.core.engine import Engine
from src.core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY
from src.core.wizard import run_config_wizard


def parse_args(argv: list) -> argparse.Namespace:
    """Parse command line arguments for a run (analysis) invocation."""
    parser = argparse.ArgumentParser(
        description="Pragma: Autonomous Web-App Archaeology",
        epilog="Run `python3 src/cli.py config` once to set up your provider/model/api key.",
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
        "markdown conversion (default: debug_logs). Pass an empty string to disable.",
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
        "--element-budget",
        type=int,
        dest="element_budget",
        help="Max components MechanicalCrawler mechanically interacts with per page per visit-pass "
        "(default: 200) - the backstop against a pathological reveal-chain, not a normal-case limit.",
    )
    parser.add_argument(
        "--max-passes-per-page",
        type=int,
        dest="max_passes_per_page",
        help="Max times to revisit the same page to keep draining its interaction frontier "
        "(default: 10) - a page with more components than --element-budget needs more than one "
        "pass; this bounds how many before giving up on a page that keeps generating new content "
        "faster than one pass can keep up with.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        dest="max_pages",
        help="Total pages to visit before stopping the crawl (default: unbounded - crawl until the "
        "URL frontier is exhausted).",
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
        "--fresh",
        dest="fresh",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Purge this site's previously recorded graph_store state before crawling "
        "(default: on; matters for --graph-store neo4j, which persists across runs). "
        "Use --no-fresh to resume a previous run's progress on a large, stable site instead.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Main execution entry point.

    Bare `python3 src/cli.py` from a real terminal launches the interactive menu
    app (navigate between analyzing a URL and configuring the pipeline, no flags
    needed). `python3 src/cli.py config` jumps straight to the setup wizard. Any
    other invocation (flags/positional URL) runs a single analysis directly, for
    scripting/automation.
    """
    argv = sys.argv[1:]
    if argv and argv[0] == "config":
        run_config_wizard()
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
        if k not in ("url", "url_flag", "config_path")
    }
    if overrides.pop("headed", False):
        overrides["headless"] = False
    overrides["url"] = url

    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)

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
        print(f"Successfully generated PRD: {result.prd_path}")
        print(f"Successfully generated component tree: {result.tree_path}")

    except Exception as exc:
        print(f"Critical error during exploration: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
