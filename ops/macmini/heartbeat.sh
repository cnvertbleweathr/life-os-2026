#!/bin/bash
# ops/macmini/heartbeat.sh — tell an outside service the Mac mini is alive.
#
# Runs every 5 minutes from the LaunchDaemon com.ons.heartbeat (installed by
# harden.sh apply), as your user, from boot — no login needed. Pings
# HEARTBEAT_URL (a healthchecks.io check) from .env:
#   - everything fine      → ping            (check stays green)
#   - something is down    → ping /fail      (alert immediately, with reason)
#   - the Mac is off/asleep/offline → no ping (healthchecks alerts after grace)
#
# Checked: Tailscale connected, cloudflared running, FastAPI and Next.js
# answering locally. FastAPI/Next.js are skipped while daily_sync is running,
# because the sync stops FastAPI on purpose.
#
# bash 3.2 compatible (macOS /bin/bash).

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$REPO/.env"
URL="$(grep -E '^HEARTBEAT_URL=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
[ -z "$URL" ] && exit 0

problems=""
add_problem() { problems="${problems:+$problems; }$1"; }

TS=""
for c in /usr/local/bin/tailscale /opt/homebrew/bin/tailscale \
         /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
  [ -x "$c" ] && { TS="$c"; break; }
done
if [ -z "$TS" ]; then
  add_problem "tailscale not installed"
elif ! "$TS" status >/dev/null 2>&1; then
  add_problem "tailscale not connected"
fi

pgrep -xq cloudflared || add_problem "cloudflared not running"

if ! pgrep -fq "scripts/daily_sync.py"; then
  curl -fsS -m 5 -o /dev/null http://127.0.0.1:8000/api/health || add_problem "FastAPI not responding"
  curl -fsS -m 5 -o /dev/null http://127.0.0.1:3000/ || add_problem "Next.js not responding"
fi

up="$(uptime | sed -E 's/.*up +//; s/, +[0-9]+ users?.*//')"
summary="$(hostname -s) up $up"

if [ -z "$problems" ]; then
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$summary; all services ok" "$URL"
else
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$summary; $problems" "$URL/fail"
fi
