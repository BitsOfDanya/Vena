#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=${VENA_DEPLOY_ROOT:-/opt/vena}
export VENA_ENV_FILE="$root/shared/.env"
export VENA_REVISION
VENA_REVISION=$(cat "$root/deployed-revision")
destination="$root/shared/backups/vena-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose --env-file "$VENA_ENV_FILE" -f "$root/current/infra/compose.yaml" \
  exec -T db pg_dump --clean --if-exists -U vena vena | gzip > "$destination.tmp"
mv "$destination.tmp" "$destination"
if [[ -d "$root/shared/dataset" ]]; then
  tar -czf "${destination%.sql.gz}.dataset.tar.gz.tmp" -C "$root/shared" dataset
  mv "${destination%.sql.gz}.dataset.tar.gz.tmp" "${destination%.sql.gz}.dataset.tar.gz"
fi
docker compose --env-file "$VENA_ENV_FILE" -f "$root/current/infra/compose.yaml" \
  exec -T ml tar -czf - -C /srv/ml inbox > "${destination%.sql.gz}.inbox.tar.gz.tmp"
mv "${destination%.sql.gz}.inbox.tar.gz.tmp" "${destination%.sql.gz}.inbox.tar.gz"
find "$root/shared/backups" -name '*.inbox.tar.gz' -mtime +14 -delete
find "$root/shared/backups" -name '*.dataset.tar.gz' -mtime +14 -delete
find "$root/shared/backups" -name '*.sql.gz' -mtime +14 -delete
