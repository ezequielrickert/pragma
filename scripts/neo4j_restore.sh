#!/usr/bin/env bash
# Restore the pragma-neo4j Community Edition database from a dump file
# written by scripts/neo4j_backup.sh (or any `neo4j-admin database dump`
# output for the same Neo4j major version).
#
# DESTRUCTIVE: overwrites whatever is currently in the neo4j container's
# data volume (pragma_neo4j_data, see docker-compose.yml) - there is no
# confirmation prompt, this script is meant to be run deliberately, not
# accidentally. Consider taking a fresh backup first (scripts/neo4j_backup.sh)
# if the current state might still be worth keeping.
#
# Usage: scripts/neo4j_restore.sh <path-to-dump-file>
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP_FILE="${1:?Usage: scripts/neo4j_restore.sh <path-to-dump-file>}"
if [ ! -f "$DUMP_FILE" ]; then
  echo "Dump file not found: $DUMP_FILE" >&2
  exit 1
fi

# neo4j-admin database load expects a directory containing a file literally
# named <database-name>.dump (neo4j.dump here), not an arbitrary filename -
# stage a copy under that exact name in a throwaway temp dir rather than
# requiring every backup file on disk to be named exactly "neo4j.dump"
# (scripts/neo4j_backup.sh deliberately timestamps its output, so this
# staging step is what lets any of those timestamped backups be restored
# directly, unchanged).
STAGING_DIR=$(mktemp -d)
trap 'rm -rf "$STAGING_DIR"' EXIT
cp "$DUMP_FILE" "$STAGING_DIR/neo4j.dump"

echo "Stopping neo4j..."
docker compose stop neo4j

echo "Loading $(basename "$DUMP_FILE") into the neo4j database - this OVERWRITES the current data..."
docker compose run --rm --no-deps \
  -v "$STAGING_DIR:/backups" \
  --entrypoint neo4j-admin \
  neo4j database load neo4j --from-path=/backups --overwrite-destination=true

echo "Restarting neo4j..."
docker compose start neo4j

echo "Restore complete."
