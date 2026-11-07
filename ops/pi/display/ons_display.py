#!/usr/bin/env python3
"""
ons_display.py: the LED panel player. Runs on the Raspberry Pi.

The Pi is dumb on purpose: ONS decides what to show (GET /api/display/playlist),
this only plays it. Each item is a URL and a number of seconds:
  - a GIF (a film's 5-second loop) plays at its own frame timing, looping for the seconds;
  - a PNG (a score card, the clock) holds for the seconds.
After each item it checks whether the playlist's refresh time has passed (30 s
while one of my teams is live, 60 s otherwise) and fetches a new one.
If the API can't be reached it keeps playing the last playlist it had.
Mode "off" (quiet hours) blanks the panel.

Hardware: a 64×32 HUB75 RGB panel on an RGB matrix HAT/bonnet, driven by
hzeller/rpi-rgb-led-matrix's Python bindings (`rgbmatrix`). See README.md.

Needs only the standard library and Pillow on the Pi (plus `rgbmatrix` for the
real panel). Settings come from flags or the environment (systemd's
EnvironmentFile, /etc/default/ons-display):

  ONS_API            http://<mac-mini-tailscale-ip>:8000   (required)
  LED_GPIO_MAPPING   adafruit-hat | adafruit-hat-pwm | regular   (default adafruit-hat)
  LED_BRIGHTNESS     1–100 (default 60)
  LED_SLOWDOWN_GPIO  0–4 (default 2; raise it if the panel flickers on a Pi 4)

Usage:
  sudo python3 ons_display.py                       # the panel, forever (what systemd runs)
  python3 ons_display.py --emulate /tmp/panel --once   # no panel: write frames as PNGs, play one playlist
"""
from __future__ import annotations

import argparse
import io
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from PIL import Image, ImageSequence

W, H = 64, 32
UA = {"User-Agent": "ons-display/1.0"}
Frames = list  # [(PIL.Image RGB 64×32, milliseconds)]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ── panels ───────────────────────────────────────────────────────────────────

class MatrixPanel:
    """The real 64×32 HUB75 panel through rpi-rgb-led-matrix."""

    def __init__(self, mapping: str, brightness: int, slowdown: int):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions   # only on the Pi
        o = RGBMatrixOptions()
        o.rows, o.cols, o.chain_length, o.parallel = H, W, 1, 1
        o.hardware_mapping = mapping
        o.brightness = brightness
        o.gpio_slowdown = slowdown
        o.drop_privileges = True                             # starts as root for GPIO, then drops to daemon
        self.matrix = RGBMatrix(options=o)
        self.canvas = self.matrix.CreateFrameCanvas()

    def show(self, img: Image.Image) -> None:
        self.canvas.SetImage(img, 0, 0)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        self.matrix.Clear()


class FilePanel:
    """No hardware: every frame shown is written to DIR (frame-000001.png …) and DIR/current.png."""

    def __init__(self, directory: Path):
        self.dir, self.n = directory, 0
        self.dir.mkdir(parents=True, exist_ok=True)

    def show(self, img: Image.Image) -> None:
        self.n += 1
        img.save(self.dir / f"frame-{self.n:06d}.png")
        img.save(self.dir / "current.png")

    def clear(self) -> None:
        Image.new("RGB", (W, H)).save(self.dir / "current.png")


# ── fetching ─────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: float = 10) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def fit(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    return img if img.size == (W, H) else img.resize((W, H), Image.NEAREST)


def decode(data: bytes) -> Frames:
    """Bytes → [(frame, ms)]. A still image is one frame; a GIF keeps its delays."""
    im = Image.open(io.BytesIO(data))
    if getattr(im, "is_animated", False):
        return [(fit(f), max(20, int(f.info.get("duration", 125)))) for f in ImageSequence.Iterator(im)]
    return [(fit(im), 1000)]


class Player:
    def __init__(self, api: str, panel, get: Callable[[str], bytes] | None = None,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.monotonic):
        self.api, self.panel, self.sleep, self.now = api.rstrip("/"), panel, sleep, now
        self.get = get or (lambda url: http_get(url))   # resolved per call, so http_get can be swapped
        self.playlist: dict | None = None
        self.media: "OrderedDict[str, Frames]" = OrderedDict()   # url → decoded frames (GIFs repeat across playlists)
        self.running = True

    def fetch_playlist(self) -> dict | None:
        try:
            pl = json.loads(self.get(f"{self.api}/api/display/playlist"))
            if pl.get("errors"):
                log(f"playlist warnings: {pl['errors'][:2]}")
            return pl
        except (urllib.error.URLError, OSError, ValueError) as e:
            log(f"playlist fetch failed ({e}); {'keeping the last one' if self.playlist else 'nothing to play yet'}")
            return None

    def load(self, url: str) -> Frames | None:
        if url in self.media:
            self.media.move_to_end(url)
            return self.media[url]
        try:
            frames = decode(self.get(self.api + url if url.startswith("/") else url))
        except Exception as e:
            log(f"skip {url}: {e}")
            return None
        self.media[url] = frames
        while len(self.media) > 48:
            self.media.popitem(last=False)
        return frames

    def play(self, frames: Frames, seconds: float) -> None:
        """Loop the frames for `seconds` (a still holds); always shows at least one full pass."""
        end = self.now() + seconds
        while self.running:
            for img, ms in frames:
                self.panel.show(img)
                self.sleep(ms / 1000 if len(frames) > 1 else min(1.0, max(0.0, end - self.now())))
                if not self.running:
                    return
            if self.now() >= end:
                return

    def cycle(self) -> None:
        """Fetch (or keep) a playlist and play it until its refresh time is up."""
        fresh = self.fetch_playlist()
        if fresh is not None:
            if not self.playlist or fresh.get("mode") != self.playlist.get("mode"):
                log(f"mode {fresh.get('mode')}: {len(fresh.get('items', []))} items")
            self.playlist = fresh
        pl = self.playlist
        if not pl:
            self.panel.clear()
            self.sleep(10)
            return
        refresh = float(pl.get("refresh_s") or 60)
        if pl.get("mode") == "off" or not pl.get("items"):
            self.panel.clear()
            self.sleep(refresh)
            return
        deadline = self.now() + refresh
        for item in pl["items"]:
            frames = self.load(item["url"])
            if frames:
                self.play(frames, float(item.get("seconds") or 8))
            if not self.running or self.now() >= deadline:
                return

    def run(self, once: bool = False) -> None:
        while self.running:
            self.cycle()
            if once:
                return


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Play the ONS display playlist on a 64×32 LED panel.")
    p.add_argument("--api", default=os.getenv("ONS_API", ""), help="e.g. http://100.64.0.10:8000")
    p.add_argument("--emulate", type=Path, help="no panel: write frames to this directory")
    p.add_argument("--once", action="store_true", help="play one playlist and exit")
    p.add_argument("--mapping", default=os.getenv("LED_GPIO_MAPPING", "adafruit-hat"))
    p.add_argument("--brightness", type=int, default=int(os.getenv("LED_BRIGHTNESS", "60")))
    p.add_argument("--slowdown", type=int, default=int(os.getenv("LED_SLOWDOWN_GPIO", "2")))
    args = p.parse_args(argv)
    if not args.api:
        p.error("set --api or ONS_API to the ONS API, e.g. http://<mac-mini-tailscale-ip>:8000")

    panel = FilePanel(args.emulate) if args.emulate else MatrixPanel(args.mapping, args.brightness, args.slowdown)
    player = Player(args.api, panel)

    def stop(*_):
        player.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log(f"ONS display → {args.api} ({'emulated: ' + str(args.emulate) if args.emulate else args.mapping})")
    try:
        player.run(once=args.once)
    finally:
        panel.clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
