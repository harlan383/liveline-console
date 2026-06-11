#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

POSTGRES_SERVICE="postgres"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="backups/local-db/${TIMESTAMP}"
BACKUP_FILE="${BACKUP_DIR}/liveline-db-${TIMESTAMP}.dump"

cleanup_failed_backup() {
  if [[ -n "${BACKUP_FILE:-}" && -f "$BACKUP_FILE" && ! -s "$BACKUP_FILE" ]]; then
    rm -f "$BACKUP_FILE"
  fi
}
trap cleanup_failed_backup ERR

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command docker

echo "Checking PostgreSQL service..."
if ! docker compose exec -T "$POSTGRES_SERVICE" sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null'; then
  echo "PostgreSQL service is not ready. Start it with: docker compose up -d postgres" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Creating local PostgreSQL backup..."
docker compose exec -T "$POSTGRES_SERVICE" sh -c \
  'pg_dump -Fc --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$BACKUP_FILE"

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "Backup file is empty; backup failed." >&2
  rm -f "$BACKUP_FILE"
  exit 1
fi

BACKUP_SIZE="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"

echo "Backup completed."
echo "Path: $BACKUP_FILE"
echo "Size bytes: $BACKUP_SIZE"
echo "Created at: $TIMESTAMP"
echo "Reminder: backups/ is local-only and must not be committed to Git."
