#!/usr/bin/env bash
set -Eeuo pipefail
compose_args=("$@")
dc() { docker compose ${compose_args[@]+"${compose_args[@]}"} "$@"; }
db() { dc exec -T db "$@"; }
now() { python3 -c 'import time; print(time.time())'; }
since() { python3 -c 'import sys; print(f"{float(sys.argv[2]) - float(sys.argv[1]):.1f}")' "$1" "${2:-$(now)}"; }
counts() {
  db psql -X -At -U vena -d vena -c "SELECT string_agg(table_name || '=' ||
    (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', table_name),
    false, true, '')))[1]::text, ' ' ORDER BY table_name)
    FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
}
recreate() {
  db dropdb -U vena --force vena
  db createdb -U vena vena
}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

before=$(counts)
echo "Rows: $before"
t0=$(now)
dc --progress quiet stop backend
t1=$(now)
db pg_dump -U vena -d vena -Fc > "$work/vena.dump"
t2=$(now)
db pg_dump -U vena -d vena --clean --if-exists | gzip > "$work/vena.sql.gz"
t3=$(now)
recreate
db pg_restore -U vena -d vena --exit-on-error < "$work/vena.dump"
t4=$(now)
[[ $(counts) == "$before" ]] || { echo 'Row counts differ after pg_restore' >&2; exit 1; }
t5=$(now)
recreate
gzip -dc "$work/vena.sql.gz" | db psql -X -q -v ON_ERROR_STOP=1 -U vena -d vena >/dev/null
t6=$(now)
[[ $(counts) == "$before" ]] || { echo 'Row counts differ after psql restore' >&2; exit 1; }
t7=$(now)
dc --progress quiet up -d --no-deps --wait backend
t8=$(now)

stop=$(since "$t0" "$t1")
custom=$(since "$t3" "$t4")
plain=$(since "$t5" "$t6")
start=$(since "$t7" "$t8")
cat <<EOF
| шаг | время, с | размер |
|---|---|---|
| остановка backend | $stop | |
| pg_dump -Fc | $(since "$t1" "$t2") | $(du -h "$work/vena.dump" | cut -f1) |
| pg_dump + gzip, как backup.sh | $(since "$t2" "$t3") | $(du -h "$work/vena.sql.gz" | cut -f1) |
| dropdb, createdb, pg_restore | $custom | |
| dropdb, createdb, gunzip, psql | $plain | |
| запуск backend до healthy | $start | |
| итого с pg_restore | $(python3 -c "print(f'{$stop + $custom + $start:.1f}')") | |
| итого с psql | $(python3 -c "print(f'{$stop + $plain + $start:.1f}')") | |
EOF
echo "PASS: row counts of every table match after both restores"
