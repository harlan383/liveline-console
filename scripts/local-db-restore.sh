#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

POSTGRES_SERVICE="postgres"

usage() {
  echo "Usage: $0 <backup-file.sql|backup-file.dump|backup-file.backup>" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "Backup file is empty: $BACKUP_FILE" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Required command not found: docker" >&2
  exit 1
fi

echo "WARNING: restoring a backup can overwrite the current local database state."
echo "Recommended first step: run scripts/local-db-backup.sh before restoring."
echo "Recommended safety window: stop app services with:"
echo "  docker compose stop backend worker frontend"
echo
read -r -p "Type RESTORE LOCAL DB to continue: " CONFIRMATION

if [[ "$CONFIRMATION" != "RESTORE LOCAL DB" ]]; then
  echo "Restore cancelled."
  exit 1
fi

echo "Checking PostgreSQL service..."
if ! docker compose exec -T "$POSTGRES_SERVICE" sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null'; then
  echo "PostgreSQL service is not ready. Start it with: docker compose up -d postgres" >&2
  exit 1
fi

case "$BACKUP_FILE" in
  *.dump|*.backup)
    echo "Restoring custom-format backup..."
    docker compose exec -T "$POSTGRES_SERVICE" sh -c \
      'pg_restore --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "$BACKUP_FILE"
    ;;
  *.sql)
    echo "Restoring SQL backup..."
    docker compose exec -T "$POSTGRES_SERVICE" sh -c \
      'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "$BACKUP_FILE"
    ;;
  *)
    echo "Unsupported backup file extension. Use .dump, .backup, or .sql." >&2
    exit 1
    ;;
esac

echo "Restore completed."
echo "Next recommended checks:"
echo "  docker compose up -d"
echo "  scripts/local-health-check.sh"
echo "  Open http://localhost:3000 and verify records manually."
