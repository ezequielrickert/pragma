#!/usr/bin/env bash
# Offline dump of the pragma-neo4j Community Edition database to backups/.
#
# Community Edition only supports an *offline* backup (the database must be
# stopped while dumping - Enterprise Edition supports a live/online backup,
# not available here) - see docs/explicativos/plan-almacenamiento.md Fase D
# and https://neo4j.com/docs/operations-manual/current/docker/dump-load/.
#
# Usage: scripts/neo4j_backup.sh
#
# Writes backups/neo4j_<UTC-timestamp>.dump - stops the neo4j container for
# the duration of the dump, restarts it afterward. Safe to run against a
# container that's already stopped (the stop/start calls are no-ops then).
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p backups
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_NAME="neo4j_${TIMESTAMP}.dump"

echo "Stopping neo4j (Community Edition only supports an offline dump)..."
docker compose stop neo4j

echo "Dumping database to backups/${BACKUP_NAME}..."
# --no-deps: this project's docker-compose.yml has no other services today,
# but this stays correct if that ever changes (no reason a backup should
# spin up unrelated services). -v adds the /backups mount just for this
# one-off run, without permanently changing docker-compose.yml's own
# volumes (the neo4j service doesn't need /backups mounted for normal
# operation, only for this script and neo4j_restore.sh).
docker compose run --rm --no-deps \
  -v "$(pwd)/backups:/backups" \
  --entrypoint neo4j-admin \
  neo4j database dump neo4j --to-path=/backups

# neo4j-admin always writes <database-name>.dump (neo4j.dump here) -
# rename to a timestamped name so repeated backups don't silently overwrite
# each other, matching this project's existing "timestamp in the filename"
# convention for every other generated artifact (docs/, debug_logs/).
mv "backups/neo4j.dump" "backups/${BACKUP_NAME}"

echo "Restarting neo4j..."
docker compose start neo4j

echo "Backup written to backups/${BACKUP_NAME}"
