"""
Input/Output utilities for Pragma.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def write_output(path_str: str, content: str) -> None:
    """Write content to a file, creating parent directories if needed.

    Args:
        path_str: Destination file path.
        content: String content to write.
    """
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def upsert_env_vars(path_str: str, values: Dict[str, str]) -> None:
    """Set one or more KEY=value lines in a .env-style file, preserving the rest.

    Existing `KEY=` lines (and any comments/blank lines) are left untouched except
    for the keys being updated; new keys are appended at the end.

    Args:
        path_str: Path to the .env file (created if it doesn't exist).
        values: Mapping of env var name to new value.
    """
    path = Path(path_str)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
