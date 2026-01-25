#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

# -----------------
# Config / Endpoints
# -----------------
WIKIMEDIA_ONTHISDAY_EVENTS = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm}/{dd}"
OPENAI_IMAGES_ENDPOINT = "https://api.openai.com/v1/images/generations"

SPOTIFY_UPLOAD_COVER = "https://api.spotify.com/v1/playlists/{playlist_id}/images"
SPOTIFY_CHANGE_DETAILS = "https://api.spotify.com/v1/playlists/{playlist_id}"

# Spotify limit: request body is BASE64 string; keep it < 256KB
MAX_SPOTIFY_BASE64_BYTES = 256 * 1024

DEFAULT_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
DEFAULT_IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")

# Retries
SPOTIFY_MAX_RETRIES = int(os.getenv("SPOTIFY_MAX_RETRIES", "6"))
SPOTIFY_BACKOFF_BASE_SEC = float(os.getenv("SPOTIFY_BACKOFF_BASE_SEC", "0.8"))
SPOTIFY_BACKOFF_CAP_SEC = float(os.getenv("SPOTIFY_BACKOFF_CAP_SEC", "12"))

OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "4"))
OPENAI_BACKOFF_BASE_SEC = float(os.getenv("OPENAI_BACKOFF_BASE_SEC", "1.0"))
OPENAI_BACKOFF_CAP_SEC = float(os.getenv("OPENAI_BACKOFF_CAP_SEC", "20"))

# Description limits (be conservative)
DEFAULT_MAX_DESC = int(os.getenv("SPOTIFY_MAX_DESC_CHARS", "280"))


# ---------------
# Helpers
# ---------------
def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"Missing {name} in environment/.env")
    return v


def _clean_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _short(s: str, n: int = 240) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 1] + "…")


def _sanitize_for_image_prompt(text: str) -> str:
    """
    Keep the image prompt safe + clean. Remove links, collapse whitespace,
    avoid graphic/violent wording where possible.
    """
    t = (text or "").strip()
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s+", " ", t).strip()

    # Soft-scrub words that sometimes trip image safety filters.
    # We still keep meaning but avoid explicit injury/death terms.
    replacements = {
        "killing": "resulting in fatalities",
        "killed": "resulting in fatalities",
        "dies": "passes away",
        "dead": "fatalities",
        "crashes": "has an accident",
        "crash": "accident",
        "explosion": "blast",
        "assassination": "attack",
        "massacre": "attack",
        "war": "conflict",
    }
    for a, b in replacements.items():
        t = re.sub(rf"\b{re.escape(a)}\b", b, t, flags=re.IGNORECASE)

    return t


def _spotify_sanitize_description(desc: str, max_len: int = DEFAULT_MAX_DESC) -> str:
    d = (desc or "").strip()
    d = re.sub(r"[\r\n\t]+", " ", d)
    d = re.sub(r"\s{2,}", " ", d).strip()

    # Remove control chars
    d = "".join(ch for ch in d if ch.isprintable())

    if len(d) > max_len:
        d = d[: max_len - 1] + "…"
    return d


def get_spotify_client() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            scope="playlist-modify-public playlist-modify-private ugc-image-upload",
            client_id=_require_env("SPOTIFY_CLIENT_ID"),
            client_secret=_require_env("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=_require_env("SPOTIFY_REDIRECT_URI"),
            cache_path=".spotify_token_cache",
        )
    )


def _spotify_headers_from_client(sp: spotipy.Spotify) -> Dict[str, str]:
    token_info = sp.auth_manager.get_cached_token()
    if not token_info:
        token_info = sp.auth_manager.get_access_token(as_dict=True)
    token = token_info["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _http_get_json(url: str, timeout: int = 30) -> dict:
    headers = {
        "User-Agent": "life-os-2026/1.0 (contact: karey.graham@gmail.com)",
        "Accept": "application/json",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _pick_event_for_date(d: date, *, seed: Optional[int] = None) -> Dict[str, Any]:
    url = WIKIMEDIA_ONTHISDAY_EVENTS.format(mm=f"{d.month:02d}", dd=f"{d.day:02d}")
    data = _http_get_json(url)

    events: List[dict] = data.get("events") or []
    if not events:
        raise RuntimeError("No events returned from Wikimedia On This Day feed.")

    scored: List[Tuple[float, dict]] = []
    for ev in events:
        year = ev.get("year")
        text = _clean_html(ev.get("text", ""))
        lower = text.lower()
        ban = ["killing", "killed", "dies", "dead", "crash", "crashes", "explosion", "massacre", "assassination", "bomb"]
        if any(w in lower for w in ban):
            continue
        if not text or not isinstance(year, int):
            continue
        if len(text) < 30 or len(text) > 240:
            continue

        pages = ev.get("pages") or []
        has_page = 1.0 if pages else 0.0

        if 1800 <= year <= 2010:
            year_score = 1.0
        elif 1500 <= year < 1800:
            year_score = 0.6
        else:
            year_score = 0.4

        cleanliness = 1.0 - (len(text) / 280.0)
        score = (1.3 * has_page) + (1.0 * year_score) + (0.7 * cleanliness)
        scored.append((score, ev))

    if not scored:
        return random.choice(events)

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [ev for _, ev in scored[: min(12, len(scored))]]

    rng = random.Random(seed if seed is not None else int(d.strftime("%Y%m%d")))
    return rng.choice(top)


def _event_to_assets(ev: Dict[str, Any], d: date) -> Tuple[str, str, str]:
    year = ev.get("year")
    raw_text = _clean_html(ev.get("text", ""))
    pages = ev.get("pages") or []

    page_title = ""
    page_extract = ""
    page_url = ""
    if pages:
        p0 = pages[0] or {}
        page_title = p0.get("normalizedtitle") or p0.get("title") or ""
        page_extract = _clean_html(p0.get("extract", ""))
        page_url = p0.get("content_urls", {}).get("desktop", {}).get("page", "") or ""

    title_text = f"On This Day: {d.strftime('%b %d')} ({year})"
    if page_title:
        title_text = f"{d.strftime('%b %d')} • {page_title} ({year})"

    safe_event = _sanitize_for_image_prompt(raw_text)

    image_prompt = (
        "Create an impressionist oil painting (Monet / Renoir-inspired) depicting this historical event, "
        "with period-appropriate clothing, architecture, and atmosphere. "
        "No text, no logos, no modern signage. "
        f"Event: {safe_event}. "
        f"Date: {d.strftime('%B %d')}, Year: {year}. "
    )
    if page_title and page_extract:
        image_prompt += f"Context: {page_title}. {_sanitize_for_image_prompt(page_extract[:220])}"

    # Description (we'll sanitize+truncate before sending to Spotify)
    bits: List[str] = []
    if page_title:
        bits.append(f"Related: {page_title}")
    if page_url:
        bits.append("Source: Wikipedia (On This Day)")

    desc = (
        f"🎨 Cover: impressionist depiction of a moment from {d.strftime('%B %d')}, {year}. "
        f"Event: {raw_text} "
    )
    if page_extract:
        desc += f"Quick context: {_short(page_extract, 180)} "
    if bits:
        desc += "Trivia: " + " • ".join(bits)

    return image_prompt, desc.strip(), title_text


def _openai_generate_image_bytes(prompt: str, *, model: str, size: str) -> bytes:
    api_key = _require_env("OPENAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    # Note: Different image models have slightly different supported params.
    # We'll keep it minimal and accept URL response.
    payload = {"model": model, "prompt": prompt, "size": size}

    last_err = None
    for attempt in range(OPENAI_MAX_RETRIES + 1):
        try:
            r = requests.post(OPENAI_IMAGES_ENDPOINT, json=payload, headers=headers, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt < OPENAI_MAX_RETRIES:
                    sleep_s = min(OPENAI_BACKOFF_CAP_SEC, OPENAI_BACKOFF_BASE_SEC * (2 ** attempt))
                    sleep_s = sleep_s * (0.7 + random.random() * 0.6)
                    time.sleep(sleep_s)
                    continue
            r.raise_for_status()
            data = r.json()

            # Most common: image URL
            item = (data.get("data") or [{}])[0]
            if "url" in item and item["url"]:
                img_url = item["url"]
                ir = requests.get(img_url, timeout=90)
                ir.raise_for_status()
                return ir.content

            # Some responses may include b64_json
            if "b64_json" in item and item["b64_json"]:
                return base64.b64decode(item["b64_json"])

            raise RuntimeError(f"OpenAI image response missing url/b64_json: {list(item.keys())}")

        except Exception as e:
            last_err = e
            if attempt >= OPENAI_MAX_RETRIES:
                raise
            sleep_s = min(OPENAI_BACKOFF_CAP_SEC, OPENAI_BACKOFF_BASE_SEC * (2 ** attempt))
            sleep_s = sleep_s * (0.7 + random.random() * 0.6)
            time.sleep(sleep_s)

    raise RuntimeError(f"OpenAI request failed: {last_err}")


def _to_jpeg_bytes(img_bytes: bytes, *, target_max_base64_bytes: int = MAX_SPOTIFY_BASE64_BYTES) -> Tuple[bytes, str]:
    """
    Returns (jpeg_bytes, base64_str) such that len(base64_str.encode('utf-8')) <= target_max_base64_bytes.
    We optimize for base64 size, not raw JPEG bytes.
    """
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError("Pillow required: pip install pillow") from e

    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    def encode(im_obj, quality: int, scale: float = 1.0) -> Tuple[bytes, str]:
        if scale != 1.0:
            w, h = im_obj.size
            im_obj = im_obj.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        out = io.BytesIO()
        im_obj.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        jb = out.getvalue()
        b64 = base64.b64encode(jb).decode("utf-8")
        return jb, b64

    # First pass: try quality ladder
    for q in [92, 88, 84, 80, 76, 72, 68, 64, 60, 56, 52, 48]:
        jb, b64 = encode(im, q, 1.0)
        if len(b64.encode("utf-8")) <= target_max_base64_bytes:
            return jb, b64

    # Second pass: downscale then try again
    for scale in [0.90, 0.85, 0.80, 0.75]:
        for q in [80, 72, 64, 56, 48]:
            jb, b64 = encode(im, q, scale)
            if len(b64.encode("utf-8")) <= target_max_base64_bytes:
                return jb, b64

    raise RuntimeError("Could not compress image to fit Spotify base64 limit.")


def _spotify_request_with_retry(method: str, url: str, *, headers: dict, json_body=None, data=None, timeout: int = 45):
    last = None
    for attempt in range(SPOTIFY_MAX_RETRIES + 1):
        try:
            r = requests.request(method, url, headers=headers, json=json_body, data=data, timeout=timeout)

            # Retry on transient issues
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt < SPOTIFY_MAX_RETRIES:
                    retry_after = r.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_s = min(SPOTIFY_BACKOFF_CAP_SEC, float(retry_after) + 0.25)
                    else:
                        sleep_s = min(SPOTIFY_BACKOFF_CAP_SEC, SPOTIFY_BACKOFF_BASE_SEC * (2 ** attempt))
                        sleep_s = sleep_s * (0.7 + random.random() * 0.6)
                    time.sleep(sleep_s)
                    continue

            if not r.ok:
                # helpful debug
                try:
                    print("Spotify error JSON:", r.json())
                except Exception:
                    print("Spotify error text:", (r.text or "")[:800])
                r.raise_for_status()

            return r

        except Exception as e:
            last = e
            if attempt >= SPOTIFY_MAX_RETRIES:
                raise
            sleep_s = min(SPOTIFY_BACKOFF_CAP_SEC, SPOTIFY_BACKOFF_BASE_SEC * (2 ** attempt))
            sleep_s = sleep_s * (0.7 + random.random() * 0.6)
            time.sleep(sleep_s)
    raise RuntimeError(f"Spotify request failed: {last}")


def _spotify_upload_cover_image(sp: spotipy.Spotify, playlist_id: str, base64_jpeg: str) -> None:
    url = SPOTIFY_UPLOAD_COVER.format(playlist_id=playlist_id)
    headers = _spotify_headers_from_client(sp)
    headers["Content-Type"] = "image/jpeg"

    _spotify_request_with_retry("PUT", url, headers=headers, data=base64_jpeg, timeout=60)


def _spotify_update_description(sp: spotipy.Spotify, playlist_id: str, description: str, *, max_len: int) -> None:
    url = SPOTIFY_CHANGE_DETAILS.format(playlist_id=playlist_id)
    headers = _spotify_headers_from_client(sp)
    headers["Content-Type"] = "application/json"

    safe_desc = _spotify_sanitize_description(description, max_len=max_len)

    _spotify_request_with_retry("PUT", url, headers=headers, json_body={"description": safe_desc}, timeout=45)


def main() -> int:
    p = argparse.ArgumentParser(description="Decorate a Spotify playlist with date-based cover art + trivia description.")
    p.add_argument("--playlist-id", required=True, help="Spotify playlist id to decorate")
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date for 'On this day' (YYYY-MM-DD)")
    p.add_argument("--seed", type=int, default=None, help="Optional RNG seed (deterministic selection)")
    p.add_argument("--dry-run", action="store_true", help="Do everything except Spotify uploads")
    p.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL, help="OpenAI image model (default from env or dall-e-3)")
    p.add_argument("--size", default=DEFAULT_IMAGE_SIZE, help="Image size, e.g. 1024x1024")
    p.add_argument("--max-desc", type=int, default=DEFAULT_MAX_DESC, help="Max playlist description length")
    args = p.parse_args()

    sp = get_spotify_client()

    d = datetime.strptime(args.date, "%Y-%m-%d").date()

    print(f"Image model: {args.image_model} | size: {args.size}")
    ev = _pick_event_for_date(d, seed=args.seed)
    prompt, desc, title = _event_to_assets(ev, d)

    print(f"Selected event: {title}")
    print(f"Description preview:\n{_spotify_sanitize_description(desc, max_len=args.max_desc)}\n")

    print("Generating image via OpenAI…")
    img = _openai_generate_image_bytes(prompt, model=args.image_model, size=args.size)

    jpeg_bytes, b64 = _to_jpeg_bytes(img, target_max_base64_bytes=MAX_SPOTIFY_BASE64_BYTES)
    print(f"JPEG bytes: {len(jpeg_bytes)} | base64 bytes: {len(b64.encode('utf-8'))} (limit {MAX_SPOTIFY_BASE64_BYTES})")

    if args.dry_run:
        print("DRY RUN: not uploading to Spotify.")
        return 0

    print("Uploading cover image to Spotify…")
    _spotify_upload_cover_image(sp, args.playlist_id, b64)

    print("Updating playlist description…")
    _spotify_update_description(sp, args.playlist_id, desc, max_len=args.max_desc)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
