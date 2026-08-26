#!/usr/bin/env bash
# Runs mypy over the whole repo in two passes, matching pyproject.toml's
# split: source under [tool.mypy] strict = true as written, tests/ (which
# has no __init__.py, so mypy sees each file as a bare top-level module and
# per-module [[tool.mypy.overrides]] globs can't target it - see the
# "tests/" note below) relaxed via CLI flags instead of config.
#
# Usage: scripts/typecheck.sh
# Exit code is mypy's combined exit code - nonzero on any error in either
# pass. Used by both `make typecheck` and the pre-commit hook
# (scripts/git-hooks/pre-commit); keep this the single source of truth for
# what "typing passes" means so the hook and a manual run never disagree.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SOURCE_DIRS=(core agents database spiders generators utils dashboard interactive analysis)
SOURCE_FILES=(cli.py conftest.py)

echo "== mypy: source (strict) =="
mypy "${SOURCE_DIRS[@]}" "${SOURCE_FILES[@]}"
source_status=$?

echo
echo "== mypy: tests/ (annotations optional, bodies still checked) =="
# tests/ is exempted from *requiring* annotations (disallow-untyped-defs/
# incomplete-defs/untyped-calls) - forcing a `-> None` onto every
# `def test_*(self):` catches no bugs. check-untyped-defs (on by
# `strict = true` in pyproject.toml, unaffected by the --allow- flags
# below) still walks every test body and catches a real type error even in
# an unannotated function.
mypy tests --allow-untyped-defs --allow-incomplete-defs --allow-untyped-calls
tests_status=$?

if [ "$source_status" -ne 0 ] || [ "$tests_status" -ne 0 ]; then
    exit 1
fi
