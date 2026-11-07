"""render_mode "plex_clip": pixelate a few seconds of your own copy of the film.

ffmpeg cuts clip_start → clip_start + 5 s at 8 fps (40 frames), centre-crops to
2:1 and scales to 64×32 with area averaging; each frame is then quantized to
the theme's closed --px-* palette with a 4×4 ordered (Bayer) dither: once to
the light tokens for gif_web, once to the dark tokens for gif_matrix.

The source is the Plex file. If the path exists on this machine (optionally
rewritten by PLEX_MEDIA_PATH_MAP="server_prefix=local_prefix"), ffmpeg reads
it directly; otherwise it streams the file from the Plex server, which needs
only the few seconds around the clip (the token goes in a header, not the URL).

These GIFs are a personal-use derivative of a copyrighted film: they live
under data/film/gifs/ (gitignored) and are served only to the owner.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from film import FRAMES, FRAME_MS, H, W
from film.canvas import BAYER4
from film.palette import tokens

FPS = 1000 // FRAME_MS          # 8
CLIP_SECONDS = FRAMES / FPS     # 5.0
DITHER_SPREAD = 32              # how far (in 0–255 units) the Bayer offset nudges each pixel


class ClipError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg") or next(
        (p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg") if Path(p).exists()), None)
    if not found:
        raise ClipError("ffmpeg not found; install it (brew install ffmpeg)")
    return found


def local_path(server_path: str) -> str | None:
    mapping = os.getenv("PLEX_MEDIA_PATH_MAP", "")
    candidates = [server_path]
    if "=" in mapping:
        src, dst = mapping.split("=", 1)
        if server_path.startswith(src):
            candidates.insert(0, dst + server_path[len(src):])
    return next((c for c in candidates if Path(c).exists()), None)


def extract_frames(source: str, start: float, headers: str | None = None) -> np.ndarray:
    """(40, 32, 64, 3) uint8 frames from `source` (a path or URL), starting at `start` s."""
    vf = (f"fps={FPS},crop='min(iw,ih*2)':'min(ih,iw/2)',"
          f"scale={W}:{H}:flags=area")
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if headers:
        cmd += ["-headers", headers]
    cmd += ["-ss", f"{start:.3f}", "-i", source, "-t", f"{CLIP_SECONDS + 1:.1f}",
            "-vf", vf, "-frames:v", str(FRAMES), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=240)
    except subprocess.TimeoutExpired as e:
        raise ClipError("ffmpeg timed out reading the clip") from e
    if proc.returncode != 0:
        raise ClipError(f"ffmpeg failed: {proc.stderr.decode(errors='replace').strip()[-300:]}")
    frame_bytes = W * H * 3
    n = len(proc.stdout) // frame_bytes
    if n == 0:
        raise ClipError("ffmpeg returned no frames (clip past the end of the file?)")
    frames = np.frombuffer(proc.stdout[:n * frame_bytes], np.uint8).reshape(n, H, W, 3)
    if n < FRAMES:                       # a short read near the end: hold the last frame
        frames = np.concatenate([frames, np.repeat(frames[-1:], FRAMES - n, axis=0)])
    return frames


def quantize(frames: np.ndarray, theme: str) -> list[Image.Image]:
    """Ordered-dither every frame to the theme's --px-* palette."""
    palette = np.array(sorted(set(tokens(theme).values())), dtype=np.float32)      # (P, 3)
    bayer = (np.array(BAYER4, dtype=np.float32) + 0.5) / 16 - 0.5                  # -0.47..0.47
    offset = np.tile(bayer, (H // 4, W // 4))[..., None] * DITHER_SPREAD            # (H, W, 1)
    out = []
    for frame in frames:
        nudged = frame.astype(np.float32) + offset
        dist = ((nudged[:, :, None, :] - palette[None, None, :, :]) ** 2).sum(-1)   # (H, W, P)
        out.append(Image.fromarray(palette[dist.argmin(-1)].astype(np.uint8), "RGB"))
    return out
