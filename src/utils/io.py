"""
Input/Output utilities for Pragma.
"""
from __future__ import annotations

from pathlib import Path


def write_output(path_str: str, content: str) -> None:
    """Write content to a file, creating parent directories if needed.

    Args:
        path_str: Destination file path.
        content: String content to write.
    """
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
