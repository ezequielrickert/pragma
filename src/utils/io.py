"""Input/Output utilities for Pragma."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def write_output(path_str: str, content: str) -> None:
    """Write content to a file, creating parent directories if needed."""
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_output(path_str: str, content: str) -> None:
    """Append content to a file (not overwrite), creating parents/file if needed."""
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


def upsert_env_vars(path_str: str, values: Dict[str, str]) -> None:
    """Set one or more KEY=value lines in a .env-style file, preserving the rest."""
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
    """Append one run's metadata to a shared, git-diffable manifest.
    Details: docs/dev/utils/io.md#record_run_manifest
    """
    manifest_path = Path(out_dir) / "runs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, List[Dict[str, Any]]] = {}
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupted manifest must never block a crawl from finishing.
            data = {}
    data.setdefault(site, []).append(entry)
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return str(manifest_path)


def generate_docs_index(out_dir: str) -> str:
    """Render `runs.json` as a browsable Markdown index, one table per site.
    Details: docs/dev/utils/io.md#generate_docs_index
    """
    manifest_path = Path(out_dir) / "runs.json"
    if not manifest_path.exists():
        return "# Pragma run index\n\nNo runs recorded yet - run an analysis first.\n"

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Same "never block on a corrupted manifest" discipline as above.
        return "# Pragma run index\n\n_(runs.json could not be read - it may be corrupted)_\n"

    lines = ["# Pragma run index", "", "Generated from `runs.json` - see `docs/README.md`.", ""]
    for site in sorted(data.keys()):
        entries = data[site]
        lines.append(f"## {site}")
        lines.append("")
        lines.append("| Timestamp (UTC) | Pages (finished/total) | Components (total, unexplored) | PRD | Tree | JSON export |")
        lines.append("|---|---|---|---|---|---|")
        for entry in reversed(entries):  # most recent run first
            def _link(key: str, label: str) -> str:
                path = entry.get(key)
                return f"[{label}]({Path(path).name})" if path else "-"

            pages = f"{entry.get('pages_finished', '?')}/{entry.get('pages_total', '?')}"
            components = f"{entry.get('components_total', '?')} ({entry.get('components_unexplored', '?')} unexplored)"
            lines.append(
                f"| {entry.get('timestamp', '?')} | {pages} | {components} "
                f"| {_link('prd_path', 'PRD')} | {_link('tree_path', 'Tree')} | {_link('export_path', 'JSON')} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def get_latest_run(out_dir: str, site: str) -> Dict[str, Any]:
    """Most recently recorded manifest entry for `site`, or `{}` if none exists."""
    manifest_path = Path(out_dir) / "runs.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = data.get(site) or []
    return entries[-1] if entries else {}
