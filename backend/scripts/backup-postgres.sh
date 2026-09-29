#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${VENA_BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CONTAINER="${VENA_DB_CONTAINER:-vena-db-1}"
DB_USER="${POSTGRES_USER:-vena}"
DB_NAME="${POSTGRES_DB:-vena}"

mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/vena-${STAMP}.sql.gz"

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --format=plain \
    | gzip -c >"$FILE"
else
  : "${PGHOST:=localhost}"
  : "${PGPORT:=5432}"
  : "${PGUSER:=$DB_USER}"
  : "${PGDATABASE:=$DB_NAME}"
  : "${PGPASSWORD:=vena}"
  export PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD
  pg_dump --no-owner --format=plain | gzip -c >"$FILE"
fi

ls -1t "$OUT_DIR"/vena-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Wrote $FILE"
echo "Restore: gunzip -c $FILE | docker exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
