#!/usr/bin/env python3
"""Report line counts per source file and flag files past the split thresholds."""

import argparse
import sys
from pathlib import Path

WATCH_THRESHOLD = 300
SPLIT_THRESHOLD = 500
OVERLOADED_THRESHOLD = 700

DEFAULT_ROOTS = ["src", "tests"]
DEFAULT_EXCLUDES = {".venv", "venv", "node_modules", "__pycache__", ".git"}


def status_for(line_count: int) -> str:
    if line_count >= OVERLOADED_THRESHOLD:
        return "OVERLOADED"
    if line_count >= SPLIT_THRESHOLD:
        return "SPLIT"
    if line_count >= WATCH_THRESHOLD:
        return "WATCH"
    return "OK"


def iter_source_files(roots: list[str], extension: str):
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob(f"*{extension}"):
            if not DEFAULT_EXCLUDES.intersection(path.parts):
                yield path


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as source_file:
        return sum(1 for _ in source_file)


def build_report(roots: list[str], extension: str) -> list[tuple[Path, int, str]]:
    rows = [(path, count_lines(path), "") for path in iter_source_files(roots, extension)]
    rows = [(path, count, status_for(count)) for path, count, _ in rows]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


def print_report(rows: list[tuple[Path, int, str]]) -> None:
    if not rows:
        print("No matching files found.")
        return
    width = max(len(str(path)) for path, _, _ in rows)
    for path, count, status in rows:
        marker = f" [{status}]" if status != "OK" else ""
        print(f"{str(path):<{width}}  {count:>5} lines{marker}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", default=DEFAULT_ROOTS, help="Directories to scan")
    parser.add_argument("--ext", default=".py", help="File extension to scan (default: .py)")
    parser.add_argument(
        "--fail-over",
        type=int,
        default=None,
        help="Exit non-zero if any file reaches this many lines (e.g. --fail-over 700)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    rows = build_report(args.roots, args.ext)
    print_report(rows)

    if args.fail_over is None:
        return 0
    offenders = [path for path, count, _ in rows if count >= args.fail_over]
    if offenders:
        print(f"\n{len(offenders)} file(s) at or above {args.fail_over} lines.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
