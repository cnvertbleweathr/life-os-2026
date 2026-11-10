"""Render a film's GIF in the API process, right after the owner saves a clip.

One worker thread, one render at a time: saving five clips in a row queues
them rather than starting five ffmpeg jobs. Job state lives in memory only;
what matters survives a restart in the catalog itself (the row stays approved,
and render_error says why the last attempt failed), so anything this process
never finished is picked up by the 9:00 sync (scripts/film_gif_render.py).

  submit(film_key)   queue a render (a no-op if one is already waiting)
  state(film_key)    "queued" | "rendering" | None
"""

from __future__ import annotations

import logging
import queue
import threading

from api import film_catalog as fc

log = logging.getLogger("ons.film")

_q: queue.Queue[str] = queue.Queue()
_state: dict[str, str] = {}
_lock = threading.Lock()
_worker: threading.Thread | None = None


def state(film_key: str) -> str | None:
    with _lock:
        return _state.get(film_key)


def submit(film_key: str) -> None:
    """Queue a render of the film's current row. If it is rendering right now,
    it is queued again, so a clip re-picked mid-render still gets made."""
    global _worker
    with _lock:
        if _state.get(film_key) == "queued":
            return
        _state[film_key] = "queued"
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="film-render", daemon=True)
            _worker.start()
    _q.put(film_key)


def render_one(film_key: str) -> None:
    """Render the film's latest row now, recording success or the reason it failed."""
    from film import render   # heavy (numpy, Pillow, yt-dlp): load on first use

    row = fc.catalog().get(film_key)
    if not row or row.get("status") != "approved":
        return
    try:
        render.render_and_record(row)
    except fc.CatalogError as e:
        if e.status == 409:   # the clip changed mid-render; its own job makes the new one
            return
        fc.mark_failed(film_key, str(e))
    except (*render.FAILURES, render.Skip) as e:
        fc.mark_failed(film_key, str(e))
    except Exception as e:   # a bug, but the page should still say something
        log.exception("film render failed for %s", film_key)
        fc.mark_failed(film_key, f"render crashed: {e}")


def _run() -> None:
    while True:
        film_key = _q.get()
        try:
            with _lock:
                if _state.get(film_key) != "queued":
                    continue
                _state[film_key] = "rendering"
            try:
                render_one(film_key)
            finally:
                with _lock:
                    if _state.get(film_key) == "rendering":
                        _state.pop(film_key, None)
        finally:
            _q.task_done()
