#!/bin/bash
# ops/macmini/offsite_backup.sh — copy the nightly DuckDB backups off the Mac mini.
#
# Runs at 02:30 from the LaunchAgent com.ons.offsite-backup, after
# backup_duckdb.py has written and verified its 02:00 copy. Settings in .env:
#
#   BACKUP_OFFSITE_DEST    where copies go. user@host:path (over SSH, e.g.
#                          kg@plex-server:ons-backups → ~/ons-backups) or a
#                          local path. Unset → the script exits 0 and does nothing.
#   BACKUP_OFFSITE_DAYS    days of copies kept at the destination (default 30).
#   HEALTHCHECK_BACKUP_URL optional healthchecks.io check: /start, then success
#                          or /fail with the reason.
#
# What it does:
#   1. Sends every data/backups/duckdb/ons_*.duckdb older than 5 minutes (so a
#      backup still being written is never copied). rsync skips files already
#      there and writes each file under a temp name, so a cut-off transfer never
#      leaves a half file under a real backup name. Nothing is deleted by rsync.
#   2. Only if the copy succeeded: deletes copies at the destination whose
#      filename date is older than BACKUP_OFFSITE_DAYS. The newest copy is
#      never deleted, and only names matching ons_YYYY-MM-DD_HHMMSS.duckdb
#      are touched.
#
# Environment overrides for tests: ONS_ENV_FILE, ONS_BACKUP_DIR.
# bash 3.2 compatible (macOS /bin/bash); the Mac's rsync is openrsync, so only
# basic flags are used.

set -u

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ONS_ENV_FILE:-$REPO/.env}"
SRC_DIR="${ONS_BACKUP_DIR:-$REPO/data/backups/duckdb}"
LOG_FILE="$(dirname "$SRC_DIR")/offsite_log.jsonl"

env_get() {
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' '
}

DEST="${BACKUP_OFFSITE_DEST:-$(env_get BACKUP_OFFSITE_DEST)}"
DAYS="${BACKUP_OFFSITE_DAYS:-$(env_get BACKUP_OFFSITE_DAYS)}"
DAYS="${DAYS:-30}"
HC_URL="${HEALTHCHECK_BACKUP_URL:-$(env_get HEALTHCHECK_BACKUP_URL)}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=20"

ts() { date "+%Y-%m-%dT%H:%M:%S"; }

ping_hc() {  # ping_hc <suffix> <body>
  [ -z "$HC_URL" ] && return 0
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$2" "$HC_URL$1" || true
}

log_json() {  # log_json <status> <detail>
  mkdir -p "$(dirname "$LOG_FILE")"
  detail="$(printf '%s' "$2" | tr '"\\\n' "'/ ")"
  printf '{"ts": "%s", "status": "%s", "dest": "%s", "detail": "%s"}\n' \
    "$(ts)" "$1" "$DEST" "$detail" >> "$LOG_FILE"
}

fail() {
  echo "$(ts) FAILED: $1" >&2
  log_json failed "$1"
  ping_hc /fail "$1"
  exit 1
}

if [ -z "$DEST" ]; then
  echo "$(ts) BACKUP_OFFSITE_DEST not set in .env; skipping."
  exit 0
fi

case "$DAYS" in
  ''|*[!0-9]*) fail "BACKUP_OFFSITE_DAYS must be a whole number, got '$DAYS'" ;;
esac
[ "$DAYS" -ge 1 ] || fail "BACKUP_OFFSITE_DAYS must be at least 1"

# Split user@host:path. A local path has no colon.
case "$DEST" in
  *:*) HOST="${DEST%%:*}"; RPATH="${DEST#*:}" ;;
  *)   HOST="";            RPATH="$DEST" ;;
esac
RPATH="${RPATH:-ons-backups}"
case "$RPATH" in
  *[!A-Za-z0-9._/~-]*) fail "destination path '$RPATH' has characters this script won't pass to a shell" ;;
esac

# run_dest <command...>: run a command where the backups live.
run_dest() {
  if [ -n "$HOST" ]; then
    # shellcheck disable=SC2086,SC2029  # word-split SSH_OPTS; expand locally on purpose
    ssh $SSH_OPTS "$HOST" "$*"
  else
    sh -c "$*"
  fi
}

ping_hc /start "$(hostname -s) offsite backup to $DEST"
echo "$(ts) Offsite backup → $DEST (keep $DAYS days)"

[ -d "$SRC_DIR" ] || fail "no local backup folder at $SRC_DIR"

FILES=""
count=0
for f in $(find "$SRC_DIR" -maxdepth 1 -type f -name 'ons_*.duckdb' -mmin +5 | sort); do
  FILES="$FILES $f"
  count=$((count + 1))
done
[ "$count" -gt 0 ] || fail "no finished backups in $SRC_DIR to copy"

run_dest "mkdir -p $RPATH" || fail "could not create $RPATH at the destination (is ${HOST:-it} reachable?)"

if [ -n "$HOST" ]; then
  target="$HOST:$RPATH/"
else
  target="$RPATH/"
fi
# shellcheck disable=SC2086  # FILES is a space-separated list of plain paths
if ! out="$(rsync -a --timeout=600 -e "ssh $SSH_OPTS" $FILES "$target" 2>&1)"; then
  fail "rsync failed: $(printf '%s' "$out" | tail -3)"
fi
echo "$(ts) Copied: $count local backup(s) present at the destination"

# ── Prune by filename date ────────────────────────────────────────────────────
cutoff="$(date -v-"${DAYS}"d +%Y-%m-%d 2>/dev/null || date -d "-${DAYS} days" +%Y-%m-%d)"
listing="$(run_dest "ls -1 $RPATH")" || fail "could not list $RPATH after copying"
names="$(printf '%s\n' "$listing" \
  | grep -E '^ons_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}\.duckdb$' | sort)"
newest="$(printf '%s\n' "$names" | tail -1)"
kept=0
pruned=""
for n in $names; do
  d="$(printf '%s' "$n" | cut -c5-14)"
  if [ "$n" != "$newest" ] && [ "$d" \< "$cutoff" ]; then
    pruned="$pruned $n"
  else
    kept=$((kept + 1))
  fi
done
if [ -n "$pruned" ]; then
  rm_cmd="cd $RPATH && rm -f$pruned"
  run_dest "$rm_cmd" || fail "copied OK but pruning failed"
  echo "$(ts) Pruned (older than $cutoff):$pruned"
fi

summary="copied $count, $kept kept at destination, pruned $(echo "$pruned" | wc -w | tr -d ' '), newest $newest"
echo "$(ts) OK: $summary"
log_json ok "$summary"
ping_hc "" "$summary"
exit 0
