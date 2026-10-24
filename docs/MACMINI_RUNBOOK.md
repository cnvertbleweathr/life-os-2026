# Mac mini Runbook — recover, harden, verify

Written 2026-10-23 after the Oct 22 outage: Tailscale **and** the Cloudflare tunnel (Error 1033) both went down, so the whole machine was off the network, and there was no way back in from outside.

The goal of this runbook: after any restart, power cut or update, the Mac mini comes back **by itself** (or with one remote step), and if it doesn't, **you hear about it** within 15 minutes.

**Time:** about 90 minutes, sitting at the Mac.
**Have ready:** an Ethernet cable, your Cloudflare dashboard login, a free [healthchecks.io](https://healthchecks.io) account, and the Tailscale admin console ([login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)).

> **Pasting into zsh:** every code block here is safe to paste as-is. There are no inline `#` comments on command lines (zsh passes them to the command as arguments).

---

## The order, at a glance

| # | Step | Why |
|---|------|-----|
| 1 | Log in, find out why it went down | Fix the actual cause, not a guess |
| 2 | Apply the patch, run tests | Code below this line depends on it |
| 3 | `harden.sh check` | See exactly what's wrong on this machine |
| 4 | Ethernet | Wake-on-LAN and remote FileVault unlock need it |
| 5 | `harden.sh apply` | Power, auto-updates, heartbeat daemon |
| 6 | Remote Login + Screen Sharing | A way in that doesn't depend on Tailscale |
| 7 | Tailscale → `tailscaled` | Connects at boot, before anyone logs in; Tailscale SSH |
| 8 | cloudflared → boot daemon | narcisystem.com tunnel comes up without a login |
| 9 | FileVault decision | The one thing that can still block a remote recovery |
| 10 | Monitoring (healthchecks.io) | Find out in 15 min, not the next time you look |
| 11 | ONS catch-up + Spotify + freshness | Data from the outage, and the Spotify fix |
| 12 | **Restart test** | Proof it all comes back without you |
| 13 | Commit and push | Keep the repo the source of truth |

---

## 1. Log in and find out why it went down

Log in at the Mac. Then:

```bash
cd ~/life-os-2026
last reboot | head -5
pmset -g log | grep -E " (Sleep|Wake|Shutdown|Start) " | tail -15
softwareupdate --history | head -5
log show --last 3d --style compact --predicate 'eventMessage CONTAINS "Previous shutdown cause"' | tail -3
```

How to read it:

- **A reboot around 2–4am plus a fresh entry in `softwareupdate --history`** means macOS installed an update and restarted, then sat at the login (or FileVault) screen. Step 5 stops this from happening on its own.
- **`Previous shutdown cause: 5`** is a normal restart, usually an update. **0 or a negative number** points to a power loss or crash. Step 5's `autorestart` covers power loss.
- **No reboot, just `Sleep` entries** means it went to sleep and dropped off the network. Step 5's `sleep 0` fixes this.

Also note the **Last seen** time for mes-mac-mini in the Tailscale admin console.

---

## 2. Apply the patch and run the tests

Pull first: everything from Oct 21 is already on GitHub. Then apply the patch file from the chat. Download it on the Mac mini, or AirDrop it from the MacBook.

```bash
cd ~/life-os-2026
git pull
git am ~/Downloads/ons-2026-10-23-macmini.mbox
uv run --with pytest pytest -q
```

Expect **26 passed**.

What the patch adds:

| File | What it does |
|---|---|
| `ops/macmini/harden.sh` | `check` (read-only report) and `apply` (power, updates, heartbeat) |
| `ops/macmini/heartbeat.sh` + plist template | Pings healthchecks.io every 5 min from boot, `/fail` with a reason if Tailscale, cloudflared, FastAPI or Next.js is down |
| `scripts/freshness_check.py` | New daily-sync step: alerts on sources that stopped updating (steps failing 2+ days, stale CFB scores, old backups) |
| `scripts/daily_sync.py` | Registers `freshness_check`; pings `HEALTHCHECK_SYNC_URL` at start and end |
| `scripts/spotify_compat.py`, `spotify_check.py` | Fixes Spotify's Feb 2026 playlist field rename (`track` → `item`) that silently emptied Bucket B and show matching; diagnostic script |
| `docs/MACMINI_RUNBOOK.md` | This file |

---

## 3. See what's wrong on this machine

```bash
bash ops/macmini/harden.sh check
```

It prints ✓ / ! / ✗ per item with the fix for each. Keep the output open; the next steps work through it. You'll come back to it in step 11.

---

## 4. Ethernet

If `check` says the default route is **Wi-Fi**, plug in Ethernet now. Then in **System Settings → Network**, drag Ethernet above Wi-Fi (… menu → Set Service Order).

Wake-on-LAN and the macOS 26 remote FileVault unlock both need a wired connection to work reliably.

---

## 5. Apply the safe fixes

```bash
bash ops/macmini/harden.sh apply
```

This asks for your password once, then:

- **Power:** never sleep, wake for network access, restart automatically after a power loss. Display sleep is left alone.
- **Updates:** macOS updates still **download**, but no longer **install and reboot** on their own. Security responses and XProtect still install automatically.
  - From now on, install updates yourself when you're at the Mac or can reach it.
  - If FileVault is on, use `sudo fdesetup authrestart` to restart: it unlocks the disk once, so the Mac comes straight back up.
- **Heartbeat:** installs `/Library/LaunchDaemons/com.ons.heartbeat.plist`. It does nothing until `HEARTBEAT_URL` is set in step 10.

---

## 6. Remote Login and Screen Sharing

In **System Settings → General → Sharing**, turn on:

- **Remote Login.** Click ⓘ and set "Allow access for" to **Only these users: kg**.
- **Screen Sharing.** Click ⓘ and allow the same user only.

These are your fallback way in that doesn't depend on Tailscale (step 9 uses them via plex-server).

---

## 7. Tailscale → `tailscaled` (runs before login)

**Why:** Tailscale's App Store and Standalone apps are both GUI apps that only connect **after someone logs in**. Only the open-source `tailscaled` runs at boot, and it's also the only macOS version that can act as a **Tailscale SSH** server ([Tailscale: three ways to run Tailscale on macOS](https://tailscale.com/docs/concepts/macos-variants)).

> Do this at the Mac, not over Tailscale. You'll be disconnected for a few minutes.

**7a. Remove the GUI app.**
1. Quit Tailscale from the menu bar.
2. Drag **Applications → Tailscale** to the Trash and empty it.
3. In **System Settings → VPN**, delete any leftover Tailscale entry.
4. Restart once (`sudo shutdown -r now`) and log back in. Tailscale's docs say to restart after removing the app.

**7b. Free the name in the admin console.** In [the machines list](https://login.tailscale.com/admin/machines), use **mes-mac-mini → … → Remove**, so the new install can reuse the name.

**7c. Install `tailscaled` as a system daemon.** Steps per [Tailscaled on macOS](https://github.com/tailscale/tailscale/wiki/Tailscaled-on-macOS):

```bash
brew install --formula tailscale
sudo "$(brew --prefix)/bin/tailscaled" install-system-daemon
sudo tailscale up --ssh --hostname=mes-mac-mini
```

The last command prints a login URL. Open it, sign in, and approve the machine.

**7d. Disable key expiry.** In the admin console, use **mes-mac-mini → … → Disable key expiry**. That way the machine can't silently drop off when its key expires.

**7e. Check it:**

```bash
tailscale status
bash ops/macmini/harden.sh check
```

The Tailscale section should be all ✓. From the **MacBook**, run `ssh kg@mes-mac-mini`. Tailscale SSH answers, and the default tailnet policy lets you into your own devices.

> **Upgrading later:** `brew upgrade tailscale` updates the CLI, but the daemon runs a copy in `/usr/local/bin`. Re-run the `install-system-daemon` line after upgrading.
> **MagicDNS on the mini:** `tailscaled` doesn't change macOS DNS. The mini only needs it to reach *other* devices by tailnet name, so you can ignore this.

---

## 8. cloudflared → boot daemon

**Why:** `cloudflared service install` *without* sudo installs a launch agent, which only starts at login. *With* sudo it installs a launch daemon that starts at boot and reads its config from `/etc/cloudflared` ([Cloudflare: run as a service on macOS](https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/macos/)).

First, find out how your tunnel is set up today:

```bash
ls ~/Library/LaunchAgents /Library/LaunchDaemons | grep -i cloudflare
ps aux | grep "[c]loudflared"
ls ~/.cloudflared
```

**If the `ps` line contains `--token`,** the tunnel is managed from the dashboard:

1. Run `cloudflared service uninstall` to remove the login-time agent.
2. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels → your tunnel → Configure** and copy the macOS install command. It looks like `sudo cloudflared service install eyJ…`.
3. Run that command.

**If `~/.cloudflared` has a `config.yml`,** the tunnel is managed locally:

```bash
cloudflared service uninstall
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/config.yml /etc/cloudflared/
sudo cp ~/.cloudflared/*.json /etc/cloudflared/
sudo nano /etc/cloudflared/config.yml
```

In the editor, change `credentials-file:` to `/etc/cloudflared/<the-uuid>.json`, save, then:

```bash
sudo cloudflared service install
sudo launchctl start com.cloudflare.cloudflared
```

**Check it (both cases):**

```bash
sudo launchctl list | grep cloudflared
tail -20 /Library/Logs/com.cloudflare.cloudflared.err.log
bash ops/macmini/harden.sh check
```

Then load narcisystem.com on your phone over mobile data.

---

## 9. FileVault: the one remaining blocker

With FileVault on, a restart stops at the unlock screen. **Nothing runs** until the disk is unlocked: no Tailscale, no cloudflared, no heartbeat. This is the trade-off to decide.

**Option A: keep FileVault (recommended; your `.env` holds API keys)**

On macOS 26 you can unlock FileVault over SSH from the **same network**, provided Remote Login is on and the Mac is wired ([write-up](https://deepakness.com/raw/remote-filevault-unlock-macos-tahoe/)). From outside, the same network means **plex-server**:

```bash
ssh <your-user>@100.99.54.56
ssh kg@mes-mac-mini.local
```

Enter your Mac password when asked. The disk unlocks and the Mac finishes booting. Tailscale, cloudflared and the heartbeat then come up on their own (steps 7, 8, 5).

ONS's FastAPI and Next.js still need a **login session**, because they're launch agents. So connect with Screen Sharing over Tailscale (`vnc://mes-mac-mini` in Finder → ⌘K) and log in.

- **Test this in step 12 while you're at the Mac.** It's a new macOS feature and worth confirming on your hardware.
- For **planned** restarts, use `sudo fdesetup authrestart` and skip the unlock entirely.

**Option B: FileVault off + automatic login**

1. **System Settings → Privacy & Security → FileVault → Turn Off.** This decrypts the disk and takes a while.
2. **System Settings → Users & Groups → Automatically log in as: kg.**

After any restart everything, ONS included, comes back with zero touches. The cost: if the Mac is stolen, the disk (and `.env`) is readable.

Whichever you choose, add a line under ROADMAP → P0 so the decision is written down.

---

## 10. Monitoring: hear about it in 15 minutes

**10a. healthchecks.io** (free plan). Create two checks:

| Check | Schedule | Grace | Pinged by |
|---|---|---|---|
| `mac-mini-heartbeat` | Simple, period **5 minutes** | **15 minutes** | `ops/macmini/heartbeat.sh` every 5 min |
| `ons-daily-sync` | Cron `0 9 * * *`, timezone **America/Denver** | **2 hours** | `daily_sync.py` at start and end |

**10b. Notifications.** Under **Integrations**, add **ntfy** (same topic as `NTFY_TOPIC` in `.env`) and keep **email** on. A heartbeat `/fail` arrives with the reason, e.g. "cloudflared not running".

**10c. Add both ping URLs to `.env`:**

```bash
nano .env
```

Add these two lines, using the ping URLs healthchecks.io shows for each check:

```
HEARTBEAT_URL=https://hc-ping.com/<heartbeat-uuid>
HEALTHCHECK_SYNC_URL=https://hc-ping.com/<daily-sync-uuid>
```

Then start the heartbeat and check it reported in:

```bash
sudo launchctl kickstart -k system/com.ons.heartbeat
sleep 5
cat /tmp/ons-heartbeat.log
```

The heartbeat check on healthchecks.io should turn green, with the body "… all services ok".

**10d. Optional:** in the Cloudflare dashboard, go to **Notifications → Add → Tunnel Health Alert** for your tunnel. This gives you a second, independent signal when narcisystem.com goes dark.

---

## 11. ONS catch-up and verification

**11a. Was the sync missed during the outage?**

```bash
ls data/daily | tail -3
cat "data/daily/$(date +%F)/health.txt"
```

If today is missing, run a full sync. It stops and restarts FastAPI by itself, and CFB steps only run on their scheduled days.

```bash
python scripts/daily_sync.py
```

**11b. Spotify** (the `track` → `item` rename):

```bash
python scripts/spotify_check.py
```

| Result | Do this |
|---|---|
| All ✓ | Nothing. Bucket B and show matching are fixed by the patch |
| Tewnidge or Deeds **owner is not you** | Spotify no longer returns items for playlists you only follow. In the Spotify app, open the playlist, select all (⌘A), right-click → **Add to playlist → New playlist**. Copy the new playlist's ID from its share link and put it in `.env` as `SPOTIFY_TEWNIDGE_PLAYLIST_ID` / `SPOTIFY_DEEDS_PLAYLIST_ID` |
| Token refresh ✗ | Run `python scripts/spotify_daily10_playlist.py --no-decorate` once and approve in the browser |

Then rebuild the two Spotify-dependent outputs:

```bash
python scripts/daily_sync.py --only spotify_daily10 sync_playlist_artists
```

Check that the Daily 10 has **10 tracks** (not 5), and that **Music → Shows → My artists** lists matches again.

**11c. Freshness:**

```bash
python scripts/freshness_check.py --no-notify --no-record
```

Right after the outage you'll see ✗ for anything that missed its window. After 11a's sync, run it again: it should be ✓, apart from steps that really are broken (e.g. `track_news_signals`, already known).

**11d. Final machine check:**

```bash
bash ops/macmini/harden.sh check
```

Expected to remain: FileVault **!** under Option A, and nothing else.

---

## 12. The restart test (the point of all this)

At the Mac, with the MacBook (or phone) beside you:

```bash
sudo shutdown -r now
```

**Don't touch the Mac.** From the MacBook:

1. **Option A:** run the plex-server → `ssh kg@mes-mac-mini.local` unlock from step 9.
2. **Within ~3 minutes:** `tailscale status` on the MacBook shows mes-mac-mini **online**.
3. **narcisystem.com:**
   - **Option B:** the full site loads.
   - **Option A:** you get a 502 until someone logs in, because the tunnel is up but FastAPI/Next.js aren't. Screen Share in (`vnc://mes-mac-mini`), log in, and it loads.
4. **healthchecks.io:** heartbeat is green again within 5 minutes of login. While the services are waiting for the login, it shows a `/fail` with "FastAPI not responding" — that's correct behaviour.

If any step fails, stop and fix it now, while you're at the machine. That's the whole reason to test here.

---

## 13. Commit and push

The FastAPI and Next.js launch agents only exist on the Mac mini; track them in the repo. **Check for secrets first.**

```bash
cp ~/Library/LaunchAgents/com.ons.fastapi.plist ~/Library/LaunchAgents/com.ons.nextjs.plist launchd/
grep -n -i -E "key|token|secret|password" launchd/com.ons.fastapi.plist launchd/com.ons.nextjs.plist
```

If the grep prints anything sensitive, remove it from the copies; the apps read `.env` anyway. Then:

```bash
git add launchd/com.ons.fastapi.plist launchd/com.ons.nextjs.plist
git commit -m "launchd: track fastapi and nextjs agents"
git push
```

---

## Next time it drops while you're away

1. **healthchecks.io tells you which case you're in.**
   - **Heartbeat `/fail` with a reason:** the Mac is up and one service is down. `ssh kg@mes-mac-mini` over Tailscale and restart that service.
   - **Heartbeat silent (missed pings):** the Mac is off, asleep or locked.
2. **If it's silent,** from plex-server run `ping -c 3 mes-mac-mini.local`.
   - **It replies:** it's at the FileVault screen. Do the SSH unlock from step 9, then Screen Share and log in.
   - **No reply:** try Wake-on-LAN (`wakeonlan <MAC>`, using the address on your router). If that fails, it's powered off and someone needs to press the button.

---

## Undo

```bash
sudo launchctl bootout system/com.ons.heartbeat
sudo rm /Library/LaunchDaemons/com.ons.heartbeat.plist
sudo pmset -a sleep 1 womp 0 autorestart 0
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool true
sudo tailscaled uninstall-system-daemon
sudo cloudflared service uninstall
```

---

## Later (not part of this session)

- **Run FastAPI/Next.js without a login session:** convert them to LaunchDaemons with `UserName`. This needs `daily_sync.py`'s FastAPI stop/start moved to the system domain (which needs root). It isn't needed under Option B.
- **Off-machine backups:** copy `data/backups/duckdb` to plex-server nightly over Tailscale (`rsync`). Today the Mac mini is the only copy.
