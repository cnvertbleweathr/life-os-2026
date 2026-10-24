#!/bin/bash
# ops/macmini/harden.sh — make the Mac mini recover on its own.
#
#   ops/macmini/harden.sh check   read-only report: what would keep ONS offline
#   ops/macmini/harden.sh apply   fix the parts that are safe to script
#                                 (asks for your password once, via sudo)
#
# apply does:
#   1. power: never sleep, wake for network access, restart after power loss
#   2. stop macOS from installing OS updates (and rebooting) on its own;
#      security responses and XProtect still install
#   3. install the heartbeat LaunchDaemon (com.ons.heartbeat)
#
# Not scripted on purpose (interactive, or would cut off a remote session):
# switching Tailscale to tailscaled, moving cloudflared to a boot daemon,
# Remote Login / Screen Sharing. See docs/MACMINI_RUNBOOK.md.
#
# bash 3.2 compatible (macOS /bin/bash).

# shellcheck disable=SC2015  # ok() is printf and always succeeds, so A && ok || bad is safe
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ME="$(id -un)"
MYUID="$(id -u)"
ISSUES=0

ok()   { printf '  \033[32m✓\033[0m  %-28s %s\n' "$1" "$2"; }
bad()  { printf '  \033[31m✗\033[0m  %-28s %s\n' "$1" "$2"; ISSUES=$((ISSUES + 1)); }
warn() { printf '  \033[33m!\033[0m  %-28s %s\n' "$1" "$2"; }
fix()  { printf '       → %s\n' "$1"; }
section() { printf '\n%s\n' "$1"; }

pmset_val() { pmset -g | awk -v k="$1" '$1==k {print $2; exit}'; }
port_open() { /usr/bin/nc -z -G 2 127.0.0.1 "$1" >/dev/null 2>&1; }
env_set()   { grep -qE "^$1=.+" "$REPO/.env" 2>/dev/null && ! grep -qE "^$1=replace_me" "$REPO/.env"; }
agent_loaded() { launchctl print "gui/$MYUID/$1" >/dev/null 2>&1; }

tailscale_bin() {
  for c in /usr/local/bin/tailscale /opt/homebrew/bin/tailscale \
           /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
    [ -x "$c" ] && { echo "$c"; return; }
  done
}

check() {
  echo "ONS Mac mini check — $(hostname -s), macOS $(sw_vers -productVersion)"

  section "Power"
  [ "$(pmset_val sleep)" = "0" ] && ok "system sleep" "never" \
    || { bad "system sleep" "$(pmset_val sleep) min"; fix "harden.sh apply"; }
  [ "$(pmset_val womp)" = "1" ] && ok "wake for network access" "on" \
    || { bad "wake for network access" "off"; fix "harden.sh apply"; }
  [ "$(pmset_val autorestart)" = "1" ] && ok "restart after power loss" "on" \
    || { bad "restart after power loss" "off"; fix "harden.sh apply"; }

  section "Updates"
  au="$(defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates 2>/dev/null)"
  [ "$au" = "0" ] && ok "auto-install macOS updates" "off" \
    || { bad "auto-install macOS updates" "on (can reboot overnight)"; fix "harden.sh apply"; }

  section "Network"
  iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
  port="$(networksetup -listallhardwareports | awk -v d="$iface" '/Hardware Port/{p=$0; sub(/Hardware Port: /,"",p)} $2==d{print p; exit}')"
  case "$port" in
    *Ethernet*) ok "default route" "$iface ($port)" ;;
    "")         bad "default route" "no network" ;;
    *)          warn "default route" "$iface ($port) — Ethernet is needed for wake-on-LAN and remote FileVault unlock" ;;
  esac

  section "FileVault & remote access"
  fv="$(fdesetup status 2>/dev/null)"
  case "$fv" in
    *"is On"*)
      major="$(sw_vers -productVersion | cut -d. -f1)"
      if [ "$major" -ge 26 ]; then
        warn "FileVault" "on — after a restart nothing runs until it's unlocked; macOS $major can unlock over SSH from the LAN (see runbook)"
      else
        bad "FileVault" "on — after a restart nothing runs until someone types the password at the Mac"
      fi ;;
    *) ok "FileVault" "off" ;;
  esac
  port_open 22   && ok "Remote Login (SSH)" "on" \
    || { bad "Remote Login (SSH)" "off"; fix "System Settings → General → Sharing → Remote Login"; }
  port_open 5900 && ok "Screen Sharing" "on" \
    || { bad "Screen Sharing" "off"; fix "System Settings → General → Sharing → Screen Sharing"; }

  section "Tailscale"
  ts="$(tailscale_bin)"
  if [ -f /Library/LaunchDaemons/com.tailscale.tailscaled.plist ] \
     || [ -f /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist ]; then
    ok "variant" "tailscaled system daemon (runs before login)"
  elif [ -d /Applications/Tailscale.app ]; then
    bad "variant" "GUI app — only connects after you log in"
    fix "runbook step 5: switch to tailscaled"
  else
    bad "variant" "not installed"
  fi
  if [ -n "$ts" ] && "$ts" status >/dev/null 2>&1; then ok "connected" "$("$ts" ip -4 2>/dev/null | head -1)"
  else bad "connected" "no"; fi
  [ -d /Applications/Tailscale.app ] && { [ -f /Library/LaunchDaemons/com.tailscale.tailscaled.plist ] \
    || [ -f /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist ]; } \
    && { bad "conflict" "GUI app and tailscaled both installed"; fix "delete /Applications/Tailscale.app"; }

  section "Cloudflare tunnel"
  if [ -f /Library/LaunchDaemons/com.cloudflare.cloudflared.plist ]; then
    ok "cloudflared service" "launch daemon (starts at boot)"
  elif [ -f "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist" ]; then
    bad "cloudflared service" "launch agent — only starts after you log in"
    fix "runbook step 6"
  else
    warn "cloudflared service" "no launchd plist found — how is it started?"
  fi
  pgrep -xq cloudflared && ok "cloudflared running" "yes" || bad "cloudflared running" "no"

  section "ONS services"
  for label in com.ons.fastapi com.ons.nextjs com.ons.daily-sync com.ons.backup-duckdb; do
    if agent_loaded "$label"; then ok "$label" "loaded"
    elif [ -f "$HOME/Library/LaunchAgents/$label.plist" ]; then
      bad "$label" "plist present but not loaded"
      fix "launchctl bootstrap gui/$MYUID ~/Library/LaunchAgents/$label.plist"
    else bad "$label" "no plist in ~/Library/LaunchAgents"; fi
  done
  for label in com.ons.fastapi com.ons.nextjs; do
    [ -f "$HOME/Library/LaunchAgents/$label.plist" ] && [ ! -f "$REPO/launchd/$label.plist" ] \
      && warn "$label in repo" "missing from launchd/ — runbook step 7"
  done
  curl -fsS -m 5 -o /dev/null http://127.0.0.1:8000/api/health && ok "FastAPI" "answering" || bad "FastAPI" "not answering"
  curl -fsS -m 5 -o /dev/null http://127.0.0.1:3000/ && ok "Next.js" "answering" || bad "Next.js" "not answering"

  section "Monitoring & config"
  [ -f /Library/LaunchDaemons/com.ons.heartbeat.plist ] && ok "heartbeat daemon" "installed" \
    || { bad "heartbeat daemon" "not installed"; fix "harden.sh apply"; }
  env_set HEARTBEAT_URL        && ok "HEARTBEAT_URL" "set"        || bad "HEARTBEAT_URL" "not set in .env"
  env_set HEALTHCHECK_SYNC_URL && ok "HEALTHCHECK_SYNC_URL" "set" || bad "HEALTHCHECK_SYNC_URL" "not set in .env"
  env_set ONS_WRITE_TOKEN      && ok "ONS_WRITE_TOKEN" "set"      || bad "ONS_WRITE_TOKEN" "not set in .env"
  env_set NTFY_TOPIC           && ok "NTFY_TOPIC" "set"           || bad "NTFY_TOPIC" "not set in .env"

  used="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
  [ "$used" -lt 85 ] && ok "disk" "${used}% used" || bad "disk" "${used}% used"

  printf '\n%s\n' "$([ "$ISSUES" -eq 0 ] && echo 'Nothing to fix.' || echo "$ISSUES issue(s).")"
  return "$ISSUES"
}

apply() {
  echo "Applying safe fixes (sudo will ask for your password)…"
  sudo -v || exit 1

  echo "• power"
  sudo pmset -a sleep 0 disksleep 0 womp 1 autorestart 1 powernap 0

  echo "• macOS updates: download but don't auto-install"
  sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
  sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool true

  echo "• heartbeat daemon"
  chmod +x "$REPO/ops/macmini/heartbeat.sh"
  dest=/Library/LaunchDaemons/com.ons.heartbeat.plist
  tmp="$(mktemp)"
  sed -e "s#__REPO__#$REPO#g" -e "s#__USER__#$ME#g" \
    "$REPO/ops/macmini/com.ons.heartbeat.plist.template" > "$tmp"
  plutil -lint "$tmp" >/dev/null || { echo "plist failed lint: $tmp"; exit 1; }
  sudo launchctl bootout system/com.ons.heartbeat 2>/dev/null
  sudo install -m 644 -o root -g wheel "$tmp" "$dest"
  rm -f "$tmp"
  sudo launchctl bootstrap system "$dest"
  env_set HEARTBEAT_URL || echo "  (HEARTBEAT_URL isn't set yet — the heartbeat does nothing until it is)"

  echo
  check
}

case "${1:-check}" in
  check) check ;;
  apply) apply ;;
  *) echo "usage: $0 [check|apply]"; exit 2 ;;
esac
