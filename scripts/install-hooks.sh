#!/usr/bin/env bash
# One-time setup: symlinks this repo's tracked git hooks (scripts/git-hooks/)
# into .git/hooks/, where git actually looks for them. .git/hooks/ itself
# isn't tracked, so every clone needs to run this once.
#
# Usage: scripts/install-hooks.sh
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
hooks_source="$repo_root/scripts/git-hooks"
hooks_target="$repo_root/.git/hooks"

for hook in "$hooks_source"/*; do
    name="$(basename "$hook")"
    ln -sf "../../scripts/git-hooks/$name" "$hooks_target/$name"
    echo "installed: $name"
done
