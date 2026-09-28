#!/usr/bin/env bash
# Upload the SMVU journal to the stand and optionally switch ML to journal mode.
# Usage: infra/scripts/upload-dataset.sh [--enable] [user@host]
# The journal is proprietary: it is copied over SSH and never enters the repository.
set -Eeuo pipefail
enable=false
if [[ ${1:-} == --enable ]]; then enable=true; shift; fi
target=${1:-vena-deploy@5.129.225.86}
root=${VENA_DEPLOY_ROOT:-/opt/vena}
source_dir=$(cd "$(dirname "$0")/../../ml/dataset" && pwd)

shopt -s nullglob
files=("$source_dir"/ext-journal-*.csv "$source_dir"/справочник_каналов_датчиков.csv)
(( ${#files[@]} > 1 )) || { echo "No journal files in $source_dir"; exit 2; }

rsync --archive --partial --progress --chmod=F644 "${files[@]}" "$target:$root/shared/dataset/"

if $enable; then
  ssh "$target" "set -e
    sed -i 's/^VENA_ML_MODE=.*/VENA_ML_MODE=journal/' $root/shared/.env
    grep -q '^VENA_ML_MODE=' $root/shared/.env || echo 'VENA_ML_MODE=journal' >> $root/shared/.env
    export VENA_ENV_FILE=$root/shared/.env VENA_REVISION=\$(cat $root/deployed-revision)
    docker compose --env-file \$VENA_ENV_FILE -f $root/current/infra/compose.yaml up -d --no-build ml backend"
  echo "Journal mode enabled. The first full pass takes tens of minutes; follow it with:"
  echo "  ssh $target 'docker logs -f vena-ml-1'"
fi
