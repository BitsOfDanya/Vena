#!/usr/bin/env bash
set -Eeuo pipefail
root=${VENA_DEPLOY_ROOT:-/opt/vena}
backup=${1:?Usage: verify-backup.sh /absolute/path/to/backup.sql.gz}
[[ -f "$backup" ]] || { echo 'Backup file not found'; exit 1; }
export VENA_ENV_FILE="$root/shared/.env"
export VENA_REVISION
VENA_REVISION=$(cat "$root/deployed-revision")
compose() { docker compose --env-file "$VENA_ENV_FILE" -f "$root/current/infra/compose.yaml" "$@"; }
verify_db="vena_restore_check_$(date +%s)_$$"
trap 'compose exec -T db dropdb --if-exists -U vena "$verify_db" >/dev/null' EXIT
gzip -t "$backup"
compose exec -T db createdb -U vena "$verify_db"
gzip -dc "$backup" | compose exec -T db psql -X -v ON_ERROR_STOP=1 -q -U vena -d "$verify_db" >/dev/null
compose exec -T db psql -X -v ON_ERROR_STOP=1 -U vena -d "$verify_db" -c \
  'SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM actions) AS actions, (SELECT count(*) FROM notifications) AS notifications;'
echo "PASS: restored backup to isolated database $verify_db; production database was not modified"
