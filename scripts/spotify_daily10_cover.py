#!/usr/bin/env python3
"""
Daily 10 cover art from a fixed VectorCraft template: same inputs → same cover.
No LLM, no moderation step.

    data/spotify/processed/daily10_latest.json ──► fill assets/templates/daily10_cover.vectorcraft
        ──► JPEG ≤ 256 KB (base64) ──► data/spotify/processed/covers/<date>.jpg ──► Spotify

    uv run python scripts/spotify_daily10_cover.py                 # today's playlist
    uv run python scripts/spotify_daily10_cover.py --dry-run       # render only, no upload
    uv run python scripts/spotify_daily10_cover.py --sample --dry-run --date 2026-11-25

COVER_MODE (env): vector (default) | ai (the old gpt-image path, spotify_daily10_decorate.py) | off.

Fail soft: if VectorCraft can't be reached or the export fails, log it and exit 0
so daily_sync carries on. The playlist description gets the Wikipedia "On This
Day" fact the AI path used, without the image.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
import math
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_daily10_cover_template import (  # noqa: E402  (template geometry lives there)
    AMBER, BG, GLOBE_C, HEADLINER, LABEL, ORANGE, ORBIT_A, ORBIT_B)
from vectorcraft_client import VectorCraft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "templates" / "daily10_cover.vectorcraft"
LATEST_JSON = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
STREAMS_CSV = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
COVERS_DIR = ROOT / "data" / "spotify" / "processed" / "covers"   # what /daily10/cover serves

MAX_B64 = 256 * 1024                    # Spotify: the base64 body must stay under 256 KB
QUALITIES = (90, 84, 78, 72, 66, 60, 52, 44)
TILT_MIN, TILT_MAX = 12.0, 32.0         # orbit tilt in degrees; the sign alternates day to day
TICKS = 10
TICK_LEN, TICK_W, SAT_D = 14.0, 4.0, 16.0


def cover_mode() -> str:
    mode = os.getenv("COVER_MODE", "vector").strip().lower()
    return mode if mode in ("vector", "ai", "off") else "vector"


# ── what goes on the cover ─────────────────────────────────────────────────────

def variation(day: str) -> dict[str, float]:
    """Date-seeded, stable across runs and machines (no Python hash randomisation).

    Tilt: 12–32°, positive on even days and negative on odd ones, so neighbours always differ.
    Satellite: an angle around the orbit; the ticks follow it, half a step behind.
    """
    h = hashlib.sha256(f"daily10:{day}".encode()).digest()
    sign = 1 if date.fromisoformat(day).toordinal() % 2 == 0 else -1
    return {
        "orbit_deg": round(sign * (TILT_MIN + (h[0] / 255) * (TILT_MAX - TILT_MIN)), 1),
        "satellite_deg": round((h[1] / 255) * 360, 1),
    }


def tick_colours(latest: dict[str, Any]) -> list[str]:
    """One per track in playlist order: amber = familiar (Bucket A), orange = new (Bucket B)."""
    tracks = latest.get("tracks") or []
    if tracks and all(t.get("bucket") in ("A", "B") for t in tracks) and len(tracks) == (
            (latest.get("bucket_a_count") or 0) + (latest.get("bucket_b_count") or 0)):
        return [AMBER if t["bucket"] == "A" else ORANGE for t in tracks][:TICKS]
    a, b = mix_counts(latest)
    return ([AMBER] * a + [ORANGE] * b)[:TICKS]


def orbit_point(deg: float) -> tuple[float, float, float, float]:
    """A point on the level orbit and its unit normal; deg counter-clockwise from 3 o'clock, y down.
    sin(deg) > 0 is the far half (above the globe's centre line)."""
    cx, cy = GLOBE_C
    t = math.radians(deg)
    x, y = cx + ORBIT_A * math.cos(t), cy - ORBIT_B * math.sin(t)
    nx, ny = ORBIT_B * math.cos(t), -ORBIT_A * math.sin(t)
    n = math.hypot(nx, ny)
    return x, y, nx / n, ny / n


def artist_play_ms(streams_csv: Path = STREAMS_CSV) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    if not streams_csv.exists():
        return totals
    with open(streams_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = " ".join((row.get("artist_name") or "").split())
            if name:
                totals[name.lower()] += int(row.get("ms_played") or 0)
    return totals


def headliners(latest: dict[str, Any], play_ms: dict[str, int], n: int = 3) -> list[str]:
    """The playlist's n most-played artists (all-time), topped up with Bucket B artists."""
    artists: list[str] = []
    for t in latest.get("tracks") or []:
        a = (t.get("artist") or "").strip()
        if a and a.lower() not in {x.lower() for x in artists}:
            artists.append(a)
    ranked = sorted(artists, key=lambda a: -play_ms.get(a.lower(), 0))
    picks = [a for a in ranked if play_ms.get(a.lower(), 0) > 0][:n]
    for a in [*(latest.get("tewnidge_artists") or []), *ranked]:
        if len(picks) >= n:
            break
        if a.lower() not in {p.lower() for p in picks}:
            picks.append(a)
    return picks[:n]


def mix_counts(latest: dict[str, Any]) -> tuple[int, int]:
    a, b = latest.get("bucket_a_count"), latest.get("bucket_b_count")
    if a is None or b is None:       # pointers written before the counts were saved
        b = len(latest.get("tewnidge_artists") or [])
        a = max(0, 10 - b)
    return int(a), int(b)


def cover_fields(latest: dict[str, Any], play_ms: dict[str, int]) -> dict[str, Any]:
    """The text fields; `headliners` stays a list until it is fitted to the frame."""
    d = date.fromisoformat(latest["date"])
    a, b = mix_counts(latest)
    return {
        "date": f"{d:%Y.%m.%d} // {d:%a}".upper(),
        "title": "DAILY 10",
        "headliners": [x.upper() for x in headliners(latest, play_ms)] or ["TODAY'S MIX"],
        "mix": f"{a} FAMILIAR · {b} NEW",
    }


SAMPLES = [
    {"tracks": [{"artist": "King Gizzard & The Lizard Wizard", "bucket": "A"}, {"artist": "Gojira", "bucket": "A"},
                {"artist": "Celia Cruz", "bucket": "B"}], "bucket_a_count": 5, "bucket_b_count": 5},
    {"tracks": [{"artist": "Radiohead", "bucket": "A"}, {"artist": "Khruangbin", "bucket": "A"},
                {"artist": "Mdou Moctar", "bucket": "B"}], "bucket_a_count": 7, "bucket_b_count": 3},
    {"tracks": [{"artist": "Omar Rodríguez-López", "bucket": "B"}, {"artist": "Gian Piero Reverberi", "bucket": "B"},
                {"artist": "Eagles", "bucket": "B"}], "bucket_a_count": 0, "bucket_b_count": 10},
]


def sample_latest(day: str) -> dict[str, Any]:
    pick = SAMPLES[date.fromisoformat(day).toordinal() % len(SAMPLES)]   # consecutive days differ
    return {"date": day, "playlist_id": None, "tewnidge_artists": [], **pick}


# ── VectorCraft ────────────────────────────────────────────────────────────────

async def _text_width(vc: VectorCraft, s: str) -> float:
    """Width of s set as the headliners are set at full size (a throwaway point-text object)."""
    h = HEADLINER
    tid = (await vc.run("text.create", {"x": 0, "y": -200, "text": s, "size": h["size"],
                                        "font": LABEL[0], "style": LABEL[1]}))["id"]
    try:
        await vc.run("text.setStyle", {"id": tid, "tracking": h["tracking"]})
        res = await vc.session.read_resource(f"vectorcraft://object/{tid}")
        return float(json.loads(res.contents[0].text)["bounds"]["width"])
    finally:
        await vc.run("edit.clear", {"ids": [tid]})


async def fit_headliners(vc: VectorCraft, names: list[str]) -> tuple[str, float]:
    """3 artists if they fit at ≥ min size; else 2; else 2 cut short with an ellipsis.
    Returns the text and the size it is set at."""
    h = HEADLINER
    room = h["w"] - 4
    widest = room * h["size"] / h["min_size"]          # full-size width that still fits at min size
    s = ""
    for k in (3, 2):
        s = " · ".join(names[:k])
        w = await _text_width(vc, s)
        if w <= widest:
            return s, min(h["size"], math.floor(h["size"] * room / w * 2) / 2)
        if len(names) <= 2:
            break
    lo, hi = 1, len(s)                                  # longest prefix that fits with "…"
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if await _text_width(vc, s[:mid].rstrip(" ·") + "…") <= widest:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip(" ·") + "…", h["min_size"]


async def _render(fields: dict[str, Any], var: dict[str, float], ticks: list[str],
                  fmt: str) -> tuple[bytes, dict[str, Any]]:
    async with VectorCraft() as vc:
        await vc.run("document.open", {"path": str(TEMPLATE)})

        async def one(name: str, kind: str) -> int:
            hits = (await vc.run("document.find", {"name": name, "kind": kind}))["matches"]
            if not hits:
                raise RuntimeError(f"template has no {kind} named {name!r}")
            return hits[0]["id"]

        head, head_size = await fit_headliners(vc, fields["headliners"])
        values = {**fields, "headliners": head}
        await vc.run("dataset.new", {"name": values["date"], "values": values})
        applied = await vc.run("dataset.select", {"name": values["date"]})
        await vc.run("text.setStyle", {"id": await one("headliners", "Type"), "size": head_size})

        # ticks then satellite, each into the half of the orbit it sits on; then tilt both halves
        halves = {"back": await one("orbit_back", "Group"), "front": await one("orbit_front", "Group")}
        step = 360 / TICKS
        marks = [(var["satellite_deg"] + step / 2 + i * step, colour) for i, colour in enumerate(ticks)]
        for deg, colour in marks:
            x, y, nx, ny = orbit_point(deg)
            r = TICK_LEN / 2
            tid = await vc.tool("draw_shape", {"shape": "line", "x1": x - nx * r, "y1": y - ny * r,
                                               "x2": x + nx * r, "y2": y + ny * r,
                                               "stroke": colour, "strokeWidth": TICK_W})
            half = "back" if math.sin(math.radians(deg)) > 0 else "front"
            await vc.run("layer.move", {"ids": [tid["id"]], "target": halves[half], "place": "inside"})
        x, y, _, _ = orbit_point(var["satellite_deg"])
        sat = await vc.tool("draw_shape", {"shape": "ellipse", "x": x - SAT_D / 2, "y": y - SAT_D / 2,
                                           "width": SAT_D, "height": SAT_D, "fill": AMBER, "stroke": BG,
                                           "strokeWidth": 3})
        half = "back" if math.sin(math.radians(var["satellite_deg"])) > 0 else "front"
        await vc.run("layer.move", {"ids": [sat["id"]], "target": halves[half], "place": "inside"})
        await vc.tool("transform", {"ids": list(halves.values()), "rotate": var["orbit_deg"],
                                    "origin": list(GLOBE_C)})
        applied = {**applied, "headliners": head, "headliner_size": head_size, "satellite_half": half}
        if fmt == "png":
            return await vc.export_bytes("png", artboard=0, scale=1), applied
        for q in QUALITIES:
            data = await vc.export_bytes("jpg", artboard=0, scale=1, quality=q, method="optimized",
                                         background="#061820")
            if len(base64.b64encode(data)) <= MAX_B64:
                return data, {**applied, "quality": q}
        raise RuntimeError(f"JPEG still over {MAX_B64} base64 bytes at quality {QUALITIES[-1]}")


def render(latest: dict[str, Any], fields: dict[str, Any], fmt: str = "jpg") -> tuple[bytes, dict[str, Any]]:
    return asyncio.run(_render(fields, variation(latest["date"]), tick_colours(latest), fmt))


# ── Spotify (reuses the playlist client and the decorate upload code) ─────────

def _wiki_get_json(url: str, timeout: int = 30) -> dict:
    import requests
    r = requests.get(url, headers={"User-Agent": "ons-daily10-cover/1.0", "Accept": "application/json"},
                     timeout=timeout)
    r.raise_for_status()
    return r.json()


def on_this_day_description(d: date) -> str | None:
    """The Wikipedia 'On This Day' fact the AI path put in the description, minus the image talk."""
    import spotify_daily10_decorate as deco
    # Reuse decorate's event picking, but fetch with a generic client name: its own
    # fetch carries a personal contact address in the User-Agent.
    deco._http_get_json = _wiki_get_json
    try:
        ev = deco._pick_event_for_date(d)
    except Exception as e:  # network or feed trouble shouldn't cost the cover
        print(f"On This Day skipped: {type(e).__name__}: {e}")
        return None
    text = deco._clean_html(ev.get("text", ""))
    page = ((ev.get("pages") or [{}])[0] or {})
    title = page.get("normalizedtitle") or page.get("title") or ""
    desc = f"📅 On this day, {d:%B} {d.day}, {ev.get('year')}: {text}"
    extract = deco._clean_html(page.get("extract", ""))
    if extract:
        desc += f" {deco._short(extract, 150)}"
    if title:
        desc += f" (Wikipedia: {title})"
    return desc


def upload(playlist_id: str, jpeg: bytes, d: date) -> None:
    import spotify_daily10_decorate as deco
    from spotify_daily10_playlist import build_spotify_client
    sp = build_spotify_client()
    deco._spotify_upload_cover_image(sp, playlist_id, base64.b64encode(jpeg).decode())
    print("uploaded cover to Spotify")
    desc = on_this_day_description(d)
    if desc:
        try:
            deco._spotify_update_description(sp, playlist_id, desc, max_len=deco.DEFAULT_MAX_DESC)
            print("updated playlist description")
        except Exception as e:
            print(f"description not updated: {type(e).__name__}: {e}")


def record(latest_path: Path, cover_name: str) -> None:
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        payload["cover_image_path"] = f"covers/{cover_name}"
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not record cover in {latest_path.name}: {e}")


def run_ai(latest: dict[str, Any], dry_run: bool) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / "spotify_daily10_decorate.py"),
           "--playlist-id", latest["playlist_id"], "--date", latest["date"], *(["--dry-run"] if dry_run else [])]
    print("COVER_MODE=ai:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="cover date YYYY-MM-DD (default: the latest playlist's date)")
    p.add_argument("--dry-run", action="store_true", help="render and save, but don't upload")
    p.add_argument("--sample", action="store_true", help="fake playlist data (implies --dry-run)")
    p.add_argument("--out", type=Path, help="write the image here instead of the covers folder")
    p.add_argument("--png", action="store_true", help="export PNG instead of JPEG (previews)")
    args = p.parse_args(argv)

    mode = cover_mode()
    if mode == "off":
        print("COVER_MODE=off: no cover")
        return 0

    if args.sample:
        latest = sample_latest(args.date or date.today().isoformat())
        args.dry_run = True
    else:
        if not LATEST_JSON.exists():
            print(f"No {LATEST_JSON.name}; nothing to cover")
            return 0
        latest = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
        if args.date and latest.get("date") != args.date:
            print(f"latest playlist is {latest.get('date')}, not {args.date}; nothing to cover")
            return 0
        today = date.today().isoformat()
        if not args.date and latest.get("date") != today:
            print(f"latest playlist is {latest.get('date')}, not today ({today}); not re-covering an old playlist")
            return 0

    if mode == "ai":
        return run_ai(latest, args.dry_run) if latest.get("playlist_id") else 0

    day = latest["date"]
    fields = cover_fields(latest, artist_play_ms())
    var = variation(day)
    print(f"cover {day}: {fields} {var}")
    try:
        data, info = render(latest, fields, "png" if args.png else "jpg")
    except Exception as e:  # fail soft: daily_sync carries on without a new cover
        print(f"cover skipped: VectorCraft render failed: {type(e).__name__}: {e}")
        return 0

    ext = "png" if args.png else "jpg"
    out = args.out or COVERS_DIR / f"{day}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"saved {out} ({len(data)} bytes, base64 {len(base64.b64encode(data))}; {info})")

    if args.dry_run or args.png or args.out:
        print("dry run: not uploading")
        return 0
    if not latest.get("playlist_id"):
        print("no playlist_id; not uploading")
        return 0
    record(LATEST_JSON, out.name)
    try:
        upload(latest["playlist_id"], data, date.fromisoformat(day))
    except Exception as e:  # expired login, network: log it, keep the sync going
        print(f"upload failed: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
