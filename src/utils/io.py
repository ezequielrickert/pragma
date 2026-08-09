"""
Input/Output utilities for Pragma.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def write_output(path_str: str, content: str) -> None:
    """Write content to a file, creating parent directories if needed.

    Args:
        path_str: Destination file path.
        content: String content to write.
    """
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_output(path_str: str, content: str) -> None:
    """Append content to a file, creating parent directories/file if needed.

    Unlike write_output, prior content is preserved - each call adds to the
    end rather than overwriting, for building an append-only log/history file.

    Args:
        path_str: Destination file path.
        content: String content to append.
    """
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


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


def record_run_manifest(out_dir: str, site: str, entry: Dict[str, Any]) -> str:
    """Append one run's metadata to a shared, git-diffable manifest under
    `out_dir` (`{out_dir}/runs.json`) - {site: [entry, ...]}, oldest first.

    Every other output document `Engine` writes (PRD, component tree, JSON
    export) is timestamped in its own *filename*, which is enough to keep
    runs from colliding but not enough to answer "what's the latest run for
    this site" or "what runs exist at all" without listing the directory and
    parsing filenames - this manifest is that missing index, cheap to keep
    since `Engine` already builds every field it needs as a side effect of
    finishing a run.

    Deliberately one shared file across every site (not one manifest per
    site) - a single small JSON file is easy to `git diff`/inspect whole,
    and the number of sites one project tracks is small enough that this
    never becomes a hot file the way `docs/{site}_*` output files already
    aren't (those keep growing with every run regardless of this manifest).

    Not safe against two processes writing concurrently (read-modify-write,
    no file lock) - acceptable for how this project runs today (one `Engine`
    per process, one CLI invocation at a time); if concurrent runs against
    the same `out_dir` ever become a real usage pattern, this needs a lock
    or a per-run-file-plus-rebuild scheme instead of a single shared file.
    """
    manifest_path = Path(out_dir) / "runs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, List[Dict[str, Any]]] = {}
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupted/partial manifest must never block a real crawl from
            # finishing and writing its actual output - start a fresh
            # manifest instead of raising, same "documentation enrichment,
            # not something correctness depends on" discipline
            # GraphPRDSynthesizer's narration failure handling already uses.
            data = {}
    data.setdefault(site, []).append(entry)
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return str(manifest_path)


def get_latest_run(out_dir: str, site: str) -> Dict[str, Any]:
    """The most recently recorded `record_run_manifest` entry for `site`, or
    `{}` if none exists (no manifest file yet, or no entry for this site) -
    the read-side counterpart, for tooling that wants "the last output for
    this site" without re-crawling or parsing `docs/` filenames.
    """
    manifest_path = Path(out_dir) / "runs.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = data.get(site) or []
    return entries[-1] if entries else {}
