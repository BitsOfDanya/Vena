#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=${VENA_DEPLOY_ROOT:-/opt/vena}
revision=${1:?Usage: deploy.sh REVISION}
[[ $revision =~ ^[a-f0-9]{40}$ ]] || { echo 'Expected a full Git commit SHA'; exit 2; }
exec 9>"$root/deploy.lock"
flock -w 1800 9
export VENA_ENV_FILE="$root/shared/.env"
export VENA_REVISION="$revision"
release="$root/releases/$revision"
if [[ ! -d $release ]]; then
  mkdir "$release"
  tar -xzf "$root/incoming/$revision.tar.gz" -C "$release" --no-same-owner --same-permissions
fi
compose() { docker compose --env-file "$VENA_ENV_FILE" -f "$release/infra/compose.yaml" "$@"; }
compose config --quiet
compose build --pull
compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

# Back up before migrations. Failed migrations are not automatically downgraded.
if [[ -n $(compose ps -q db) ]]; then
  compose exec -T db pg_dump --clean --if-exists -U vena vena | gzip > "$root/shared/backups/pre-$revision.sql.gz"
fi
previous=$(cat "$root/deployed-revision" 2>/dev/null || true)
rollback() {
  echo "Deployment $revision failed; restoring previous application containers" >&2
  if [[ -n $previous && $previous != "$revision" && -d $root/releases/$previous ]]; then
    VENA_REVISION="$previous" docker compose --env-file "$VENA_ENV_FILE" \
      -f "$root/releases/$previous/infra/compose.yaml" up -d --no-build --wait --wait-timeout 300 || true
  fi
}
trap rollback ERR
compose up -d --no-build --remove-orphans --wait --wait-timeout 300
compose exec -T backend python - < "$release/infra/scripts/smoke.py"
ln -sfn "$release" "$root/current"
printf '%s\n' "$revision" > "$root/deployed-revision"
trap - ERR
echo "Deployed $revision"
compose ps
