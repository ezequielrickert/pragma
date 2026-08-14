"""Interactive, menu-driven front end for Pragma, launched with no CLI args.
Details: docs/dev/core/app.md#module
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from . import prompts
from .config import PragmaConfig
from .wizard import run_config_wizard

# Always runs in a subprocess - a scrape in-process breaks later prompts.
# Details: docs/dev/core/app.md#cli_path
CLI_PATH = Path(__file__).resolve().parents[2] / "src" / "cli.py"

ANALYZE = "Analyze a URL"
CONFIGURE = "Configure (provider, model, api key, ...)"
VIEW = "View current configuration"
EXIT = "Exit"

# Relevant secrets per provider, for "View current configuration" only.
SECRET_ENV_VARS: Dict[str, List[str]] = {
    "local": [],
    "mock": [],
}


def _print_config(config: PragmaConfig) -> None:
    print("\nCurrent configuration:")
    print(f"  agent:          {config.agent}")
    print(f"  graph_store:    {config.graph_store}")
    print(f"  out_dir:        {config.out_dir}")
    print(f"  headless:       {config.headless}")
    print(f"  wait_seconds:   {config.wait_seconds}")
    print(f"  debug_logs_dir: {config.debug_logs_dir or '(disabled)'}")
    print(f"  debug_logs_keep_last: {config.debug_logs_keep_last if config.debug_logs_keep_last else '(unbounded)'}")
    print(f"  export_json:    {config.export_json}")
    print(f"  tree_ascii:     {config.tree_ascii}")
    print(f"  max_pages:      {config.max_pages}")

    provider_options = config.agents.get(config.agent, {})
    if provider_options:
        print(f"  agents.{config.agent}:")
        for key, value in provider_options.items():
            print(f"    {key}: {value}")

    for env_name in SECRET_ENV_VARS.get(config.agent, []):
        status = "set" if os.getenv(env_name) else "not set"
        print(f"  {env_name}: {status}")
    print()


def _run_analysis() -> None:
    config = PragmaConfig.load()
    url = prompts.text("URL to analyze", default=config.url)
    if not url:
        print("No URL provided, cancelled.\n")
        return

    print()
    result = subprocess.run([sys.executable, str(CLI_PATH), url])
    if result.returncode != 0:
        print(f"\nAnalysis exited with an error (code {result.returncode}).\n")
    else:
        print()


def run_app() -> None:
    """Run the interactive menu loop until the user chooses to exit."""
    print("Pragma - Autonomous Web-App Archaeology\n")

    while True:
        try:
            choice = prompts.select(
                "What would you like to do?",
                [ANALYZE, CONFIGURE, VIEW, EXIT],
                default=ANALYZE,
                allow_custom=False,
            )
        except KeyboardInterrupt:
            break

        if choice == EXIT:
            break
        if choice == ANALYZE:
            _run_analysis()
        elif choice == CONFIGURE:
            run_config_wizard()
        elif choice == VIEW:
            _print_config(PragmaConfig.load())

    print("Goodbye.")
