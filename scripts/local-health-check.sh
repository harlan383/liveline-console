#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Required command not found: docker" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Required command not found: curl" >&2
  exit 1
fi

echo "Docker Compose services:"
docker compose ps

echo
echo "Backend health: $HEALTH_URL"
HEALTH_RESPONSE="$(curl -fsS "$HEALTH_URL")"

if command -v jq >/dev/null 2>&1; then
  echo "$HEALTH_RESPONSE" | jq .
  echo
  echo "Component status:"
  echo "$HEALTH_RESPONSE" | jq -r '.data | to_entries[] | "\(.key): \(.value.status)"'
else
  echo "$HEALTH_RESPONSE"
  echo
  echo "jq is not installed; raw health JSON printed."
fi
