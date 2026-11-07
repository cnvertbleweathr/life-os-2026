# ONS LED panel (Raspberry Pi)

Phase 5 of `docs/film/ONS_FILM_SECTION_PLAN.md`. A 64×32 RGB LED panel that
plays the film loops from the Screening Room and your teams' scores. ONS does
all the deciding (`GET /api/display/playlist` on the Mac mini); the Pi only
plays what it's told.

## What it shows
- **One of your teams is live:** that game's score card, refreshed every 30 s.
  Live games pre-empt the films.
- **Otherwise:** the rendered film loops (the dark-palette `gif_matrix` versions,
  15 s each), with a score card after every two films: later today, recent
  finals, next games.
- **Nothing rendered and no games:** the date and time.
- **Quiet hours:** set `DISPLAY_QUIET_HOURS=23-7` in the Mac mini's `.env` and
  the panel goes dark overnight. The Pi needs no change.

## Hardware
- A 64×32 HUB75 RGB LED panel (P3 or P4 pitch). 64×32 matches the film loops
  pixel for pixel.
- A Raspberry Pi (a Pi 4 or a Zero 2 W is plenty) with an RGB matrix HAT or
  bonnet (e.g. the Adafruit RGB Matrix Bonnet).
- A 5 V supply for the panel: 4 A covers a full-white 64×32 panel.

## Install on the Pi
```sh
# 1. The panel driver and its Python bindings
sudo apt install -y git python3-dev python3-pil cython3
git clone https://github.com/hzeller/rpi-rgb-led-matrix
cd rpi-rgb-led-matrix && make build-python PYTHON=$(command -v python3) && sudo make install-python PYTHON=$(command -v python3)

# 2. Turn off on-board sound (it shares the PWM hardware the panel needs)
echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf && sudo reboot

# 3. The player, its settings, and the service
sudo mkdir -p /opt/ons-display
sudo cp ons_display.py /opt/ons-display/
sudo cp ons-display.env.example /etc/default/ons-display   # then set ONS_API
sudo cp ons-display.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ons-display
journalctl -u ons-display -f
```

The Pi must be on your Tailscale network so it can reach the Mac mini's API.

## Try it without a panel
From the repo (its venv has Pillow), on any machine that can reach the API:
```sh
uv run python ops/pi/display/ons_display.py --api http://127.0.0.1:8000 --emulate /tmp/panel --once
```
Each frame lands in `/tmp/panel/` as a PNG, and `current.png` is what the panel is
showing.

## Troubleshooting
- **Flicker or ghosting:** raise `LED_SLOWDOWN_GPIO` (Pi 4: 2–4).
- **Wrong colours or a garbled image:** check `LED_GPIO_MAPPING` against your HAT.
- **Black panel:** `journalctl -u ons-display` shows the playlist mode. `off`
  means quiet hours; fetch errors mean the Pi can't reach `ONS_API`.
