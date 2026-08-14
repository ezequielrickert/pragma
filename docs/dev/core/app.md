# `core/app.py`

## module

Launched when `python3 cli.py` is run with no arguments from a real
terminal. Lets you navigate between running an analysis and
(re)configuring the pipeline without needing to remember flags or
subcommands - like the menu-driven UX of the Claude Code / GitHub
Copilot CLIs.

## cli_path

The actual scrape+generate work always runs in a subprocess (`cli.py
<url>`) rather than in-process. Playwright's sync API leaves this
process's asyncio event loop in a state that breaks subsequent
questionary prompts if a scrape runs directly in the menu process - a
known Playwright/prompt_toolkit conflict.
