#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=${VENA_DEPLOY_ROOT:-/opt/vena}
export VENA_ENV_FILE="$root/shared/.env"
export VENA_REVISION
VENA_REVISION=$(cat "$root/deployed-revision")
destination="$root/shared/backups/vena-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose --env-file "$VENA_ENV_FILE" -f "$root/current/infra/compose.yaml" \
  exec -T db pg_dump -U vena vena | gzip > "$destination.tmp"
mv "$destination.tmp" "$destination"
find "$root/shared/backups" -name '*.sql.gz' -mtime +14 -delete
