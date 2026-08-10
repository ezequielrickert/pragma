"""Thin interactive-prompt wrapper: questionary if attached to a TTY, else input().
Details: docs/dev/core/prompts.md#module
"""
from __future__ import annotations

import getpass
import sys
from typing import List, Optional

try:
    import questionary
except ImportError:
    questionary = None

CUSTOM_OPTION = "Other (type a value)..."


def _interactive() -> bool:
    return questionary is not None and sys.stdin.isatty()


def _select_interactive(message: str, options: List[str], default: Optional[str]) -> str:
    answer = questionary.select(message, choices=options, default=default).ask()
    if answer is None:
        raise KeyboardInterrupt("Prompt cancelled")
    if answer == CUSTOM_OPTION:
        return (questionary.text("Enter value:").ask() or "").strip()
    return answer


def _select_fallback(message: str, options: List[str], default: Optional[str]) -> str:
    print(message)
    for i, opt in enumerate(options, 1):
        marker = "  <- default" if opt == default else ""
        print(f"  {i}) {opt}{marker}")

    default_idx = options.index(default) + 1 if default else None
    prompt = f"Choice [1-{len(options)}]" + (f" ({default_idx})" if default_idx else "") + ": "
    raw = input(prompt).strip()

    if not raw and default:
        return default
    if not (raw.isdigit() and 1 <= int(raw) <= len(options)):
        return raw  # treat free-typed text as a custom value

    chosen = options[int(raw) - 1]
    if chosen == CUSTOM_OPTION:
        return input("Enter value: ").strip()
    return chosen


def select(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
    allow_custom: bool = True,
) -> str:
    """Prompt the user to pick from `choices` (arrow keys), or type a custom value via "Other"."""
    options = list(dict.fromkeys(choices))  # de-dupe, preserve order
    if allow_custom:
        options.append(CUSTOM_OPTION)
    default = default if default in options else None

    if _interactive():
        return _select_interactive(message, options, default)
    return _select_fallback(message, options, default)


def text(message: str, default: Optional[str] = None) -> str:
    """Prompt for free text, pre-filled with `default` when the terminal supports it."""
    if _interactive():
        answer = questionary.text(message, default=default or "").ask()
        return (answer if answer is not None else (default or "")).strip()
    raw = input(f"{message}" + (f" [{default}]" if default else "") + ": ").strip()
    return raw or (default or "")


def secret(message: str) -> str:
    """Prompt for a secret value (API key, credentials path), masked when possible."""
    if _interactive():
        return (questionary.password(message).ask() or "").strip()
    return getpass.getpass(f"{message}: ").strip()


def confirm(message: str, default: bool = True) -> bool:
    """Prompt for a yes/no answer."""
    if _interactive():
        return bool(questionary.confirm(message, default=default).ask())
    raw = input(f"{message} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")
