"""Interactive, menu-driven front end for Pragma.

Launched when `python3 src/cli.py` is run with no arguments from a real
terminal. Lets you navigate between running an analysis and (re)configuring
the pipeline without needing to remember flags or subcommands - like the
menu-driven UX of the Claude Code / GitHub Copilot CLIs.
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

# The actual scrape+generate work always runs in a subprocess (`src/cli.py <url>`)
# rather than in-process. Playwright's sync API leaves this process's asyncio
# event loop in a state that breaks subsequent questionary prompts if a scrape
# runs directly in the menu process - a known Playwright/prompt_toolkit conflict.
CLI_PATH = Path(__file__).resolve().parents[2] / "src" / "cli.py"

ANALYZE = "Analyze a URL"
CONFIGURE = "Configure (provider, model, api key, ...)"
VIEW = "View current configuration"
EXIT = "Exit"

# Which env vars are relevant secrets for each provider, purely for the "View
# current configuration" status display (never printed, only "set"/"not set").
SECRET_ENV_VARS: Dict[str, List[str]] = {
    "gemini": ["GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
    "openai": ["OPENAI_API_KEY"],
    "local": [],
    "mock": [],
}


def _print_config(config: PragmaConfig) -> None:
    print("\nCurrent configuration:")
    print(f"  scraper:        {config.scraper}")
    print(f"  agent:          {config.agent}")
    print(f"  generator:      {config.generator}")
    print(f"  out_dir:        {config.out_dir}")
    print(f"  logs_dir:       {config.logs_dir}")
    print(f"  headless:       {config.headless}")
    print(f"  max_iterations: {config.max_iterations}")

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
