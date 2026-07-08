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
from src.core.config import PragmaConfig
from src.core.engine import Engine
from src.core.registry import AGENT_REGISTRY, GENERATOR_REGISTRY, SCRAPER_REGISTRY


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Pragma: Autonomous Web-App Archaeology")
    parser.add_argument("--url", "-u", help="URL to explore")
    parser.add_argument("--config", "-c", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--scraper", help=f"Scraper plugin ({', '.join(SCRAPER_REGISTRY.names())})"
    )
    parser.add_argument(
        "--agent",
        "--provider",
        "-p",
        dest="agent",
        help=f"Agent plugin ({', '.join(AGENT_REGISTRY.names())})",
    )
    parser.add_argument(
        "--generator", "-g", help=f"Generator strategy ({', '.join(GENERATOR_REGISTRY.names())})"
    )
    parser.add_argument("--out", "-o", dest="out_dir", help="Output folder for PRDs")
    parser.add_argument("--logs", "-l", dest="logs_dir", help="Folder for research logs")
    parser.add_argument("--max-iterations", type=int, dest="max_iterations")
    parser.add_argument("--headed", action="store_true", help="Run browser with visible UI")
    return parser.parse_args()


def main() -> None:
    """Main execution entry point."""
    args = parse_args()
    overrides = {k: v for k, v in vars(args).items() if k != "config"}
    if overrides.pop("headed", False):
        overrides["headless"] = False
    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config)

    if not config.url:
        print("Error: URL must be provided via --url, YAML config, or URL env var")
        sys.exit(2)

    try:
        print(f"Starting autonomous archaeology for: {config.url}")
        print(
            f"Wiring: scraper={config.scraper} agent={config.agent} "
            f"generator={config.generator}"
        )
        engine = Engine.from_config(config)
        prd_path = engine.run(config.url)
        print(f"Successfully generated PRD: {prd_path}")

    except Exception as exc:
        print(f"Critical error during exploration: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
