#!/usr/bin/env bash
# Start a local PostgreSQL 16 cluster for development (no Docker needed).
#
#   PG_ADMIN_PASSWORD=... scripts/local_postgres.sh start   # init (first time) + start
#   scripts/local_postgres.sh stop
#
# The cluster lives outside the repository (PGDATA_DIR, default
# ~/.local/share/ai-coach-postgres) and listens on 127.0.0.1:${PGPORT:-5433}.
# Authentication is scram-sha-256 for every connection; the admin password is
# read from the environment and never written to the repository.
set -euo pipefail

PGBIN="${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"
PGDATA_DIR="${PGDATA_DIR:-$HOME/.local/share/ai-coach-postgres}"
PGPORT="${PGPORT:-5433}"

run_as_pg() {
  # initdb/postgres refuse to run as root; use the postgres system user if needed.
  if [ "$(id -u)" = "0" ]; then runuser -u postgres -- "$@"; else "$@"; fi
}

case "${1:-start}" in
  start)
    if [ ! -f "$PGDATA_DIR/PG_VERSION" ]; then
      : "${PG_ADMIN_PASSWORD:?Set PG_ADMIN_PASSWORD (superuser password of the new cluster)}"
      mkdir -p "$PGDATA_DIR"
      [ "$(id -u)" = "0" ] && chown postgres:postgres "$PGDATA_DIR"
      pwfile="$(mktemp)"; printf '%s' "$PG_ADMIN_PASSWORD" > "$pwfile"
      [ "$(id -u)" = "0" ] && chown postgres "$pwfile"
      run_as_pg "$PGBIN/initdb" -D "$PGDATA_DIR" -U postgres --pwfile="$pwfile" \
        --auth=scram-sha-256 --encoding=UTF8 --locale=C.UTF-8 >/dev/null
      rm -f "$pwfile"
    fi
    run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA_DIR" -l "$PGDATA_DIR/server.log" \
      -o "-p $PGPORT -c listen_addresses=127.0.0.1 -k /tmp" -w start
    echo "PostgreSQL running on 127.0.0.1:$PGPORT"
    ;;
  stop)
    run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA_DIR" -w stop
    ;;
  *)
    echo "usage: $0 start|stop" >&2; exit 2;;
esac
