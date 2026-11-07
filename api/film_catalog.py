"""
api/film_catalog.py: the film scene catalog, one row per film.

The catalog is the reference record for each film's 5-second pixel GIF: which
scene it shows, how it will be rendered, and where it is in the review flow:

  suggested ──approve──▶ approved ──render──▶ rendered
      │                     ▲    ◀──edit────────┘   (editing a rendered row re-queues it)
      └──reject──▶ rejected ┘                       (a rejected row can be edited and approved later)

Storage follows the ONS write path (see api/store.py): the API never writes to
DuckDB, so every change appends a full snapshot of the film's row to
data/film/scene_catalog.jsonl, and the latest snapshot per film_key wins. The
daily sync mirrors the latest rows into film.scene_catalog
(pipelines/film_catalog_pipeline.py). Nothing is ever rebuilt by dbt, and the
JSONL history keeps every edit.

Writers:
  scripts/film_suggest_scenes.py   new rows, status "suggested" (daily sync, after dbt)
  api/routers/film.py              approve / edit / reject (owner only)
  scripts/film_catalog.py          the same three from the command line
  scripts/film_gif_render.py       marks approved rows rendered (daily sync, after suggestions)

Render mode is decided by rule, not by the model (copyright matters too much
to leave to a suggestion):
  sprite     a hand-built pixel scene; only for films in the US public domain
  plex_clip  pixelated from your own Plex file; needs the file
  motif      an original mood loop; always allowed
"""

from __future__ import annotations

from datetime import date
from typing import Any

from api.store import JsonlLog, timestamp, today_local

CATALOG_LOG = JsonlLog("film", "scene_catalog.jsonl")

STATUSES = ("suggested", "approved", "rejected", "rendered")
RENDER_MODES = ("sprite", "plex_clip", "motif")
LOOP_MAX_SECONDS = 10   # a plex_clip window; the GIF itself is 5s, so leave room to choose

# Later films in the US public domain (lapsed or never-registered copyright).
# Matched on lower-cased title + release year. Deliberately short and
# conservative: add to it only for films whose status is well established.
PUBLIC_DOMAIN_LATER: frozenset[tuple[str, int]] = frozenset({
    ("night of the living dead", 1968),
    ("carnival of souls", 1962),
    ("his girl friday", 1940),
    ("charade", 1963),
    ("detour", 1945),
    ("d.o.a.", 1949),
    ("the little shop of horrors", 1960),
    ("reefer madness", 1936),
})

FIELDS = (
    "film_key", "tmdb_id", "title", "year",
    "scene_label", "scene_note", "suggested_timestamp_s", "suggestion_confidence",
    "render_mode", "clip_start", "clip_end", "plex_file",
    "status", "gif_web", "gif_matrix",
    "suggested_by", "suggested_at", "approved_at", "rejected_at", "rendered_at",
    "updated_at",
)

EDITABLE = ("scene_label", "scene_note", "render_mode", "clip_start", "clip_end")


class CatalogError(ValueError):
    """A change the catalog refuses. `status` is the HTTP code the API returns."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ── rules ────────────────────────────────────────────────────────────────────

def public_domain_through(today: date | None = None) -> int:
    """Last release year in the US public domain: works enter it 95 years after
    publication, on the following 1 January (1930 films on 1 Jan 2026)."""
    return (today or today_local()).year - 96


def is_public_domain(title: str | None, year: int | None, today: date | None = None) -> bool:
    if not year:
        return False
    if year <= public_domain_through(today):
        return True
    return ((title or "").strip().lower(), int(year)) in PUBLIC_DOMAIN_LATER


def default_render_mode(title: str | None, year: int | None, plex_file: str | None,
                        today: date | None = None) -> str:
    if is_public_domain(title, year, today):
        return "sprite"
    if plex_file:
        return "plex_clip"
    return "motif"


def check_render_mode(row: dict[str, Any]) -> None:
    """Raise CatalogError if the row's render mode and clip window aren't allowed."""
    mode = row.get("render_mode")
    if mode not in RENDER_MODES:
        raise CatalogError(f"render_mode must be one of {', '.join(RENDER_MODES)}")
    if mode == "sprite" and not is_public_domain(row.get("title"), row.get("year")):
        raise CatalogError(
            "sprite is only for films in the US public domain "
            f"(released through {public_domain_through()}, or on the PUBLIC_DOMAIN_LATER list); "
            "use plex_clip or motif"
        )
    if mode == "plex_clip":
        if not row.get("plex_file"):
            raise CatalogError("plex_clip needs the film's file in Plex, and none is known; use motif")
        start, end = row.get("clip_start"), row.get("clip_end")
        if start is not None or end is not None:
            if start is None or end is None:
                raise CatalogError("set both clip_start and clip_end")
            if start < 0 or end <= start:
                raise CatalogError("clip_end must be after clip_start, and clip_start >= 0")
            if end - start > LOOP_MAX_SECONDS:
                raise CatalogError(f"the clip window can be at most {LOOP_MAX_SECONDS}s")


# ── reads ────────────────────────────────────────────────────────────────────

def catalog() -> dict[str, dict[str, Any]]:
    """Latest row per film_key."""
    return CATALOG_LOG.latest_by("film_key")


def get(film_key: str) -> dict[str, Any]:
    row = catalog().get(film_key)
    if row is None:
        raise CatalogError(f"no catalog row for {film_key}", status=404)
    return row


# ── writes ───────────────────────────────────────────────────────────────────

def _write(row: dict[str, Any]) -> dict[str, Any]:
    row = {k: row.get(k) for k in FIELDS}
    row["updated_at"] = timestamp()
    return CATALOG_LOG.append(row)


def add_suggestion(film: dict[str, Any], suggestion: dict[str, Any] | None, suggested_by: str) -> dict[str, Any]:
    """A new row for a film with none. `film` has film_key, tmdb_id, title, year,
    plex_file; `suggestion` has scene_label, scene_note, timestamp_s, confidence,
    or is None when the model offered nothing (the row still lands, so the film
    isn't asked about again, and can be filled in by hand)."""
    if film["film_key"] in catalog():
        raise CatalogError(f"{film['film_key']} already has a catalog row", status=409)
    suggestion = suggestion or {}
    mode = default_render_mode(film.get("title"), film.get("year"), film.get("plex_file"))
    ts = suggestion.get("timestamp_s")
    clip_start = clip_end = None
    if mode == "plex_clip" and isinstance(ts, (int, float)) and ts >= 0:
        clip_start, clip_end = float(ts), float(ts) + 5
    return _write({
        **{k: film.get(k) for k in ("film_key", "tmdb_id", "title", "year", "plex_file")},
        "scene_label":           suggestion.get("scene_label"),
        "scene_note":            suggestion.get("scene_note"),
        "suggested_timestamp_s": ts,
        "suggestion_confidence": suggestion.get("confidence"),
        "render_mode":           mode,
        "clip_start":            clip_start,
        "clip_end":              clip_end,
        "status":                "suggested",
        "suggested_by":          suggested_by,
        "suggested_at":          timestamp(),
    })


def _apply_edits(row: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    unknown = set(edits) - set(EDITABLE)
    if unknown:
        raise CatalogError(f"can't edit {', '.join(sorted(unknown))}")
    new = {**row, **edits}
    for key in ("scene_label", "scene_note"):
        if isinstance(new.get(key), str):
            new[key] = new[key].strip() or None
    if edits.get("render_mode") and edits["render_mode"] != "plex_clip" \
            and "clip_start" not in edits and "clip_end" not in edits:
        new["clip_start"] = new["clip_end"] = None   # a clip window means nothing outside plex_clip
    check_render_mode(new)
    return new


def edit(film_key: str, edits: dict[str, Any]) -> dict[str, Any]:
    """Edit a row. Editing a rendered row sends it back to approved and clears
    its GIF paths, so the renderer makes it again on the next run."""
    row = get(film_key)
    new = _apply_edits(row, edits)
    if row["status"] == "rendered":
        new = {**new, "status": "approved", "gif_web": None, "gif_matrix": None, "rendered_at": None}
    return _write(new)


def approve(film_key: str, edits: dict[str, Any] | None = None) -> dict[str, Any]:
    row = get(film_key)
    if row["status"] in ("approved", "rendered"):
        raise CatalogError(f"{film_key} is already {row['status']}", status=409)
    new = _apply_edits(row, edits or {})
    if not new.get("scene_label"):
        raise CatalogError("give the scene a label before approving it")
    if new["render_mode"] == "plex_clip" and new.get("clip_start") is None:
        raise CatalogError("plex_clip needs clip_start and clip_end before approval")
    return _write({**new, "status": "approved", "approved_at": timestamp(), "rejected_at": None})


def reject(film_key: str) -> dict[str, Any]:
    row = get(film_key)
    return _write({**row, "status": "rejected", "rejected_at": timestamp(), "approved_at": None,
                   "gif_web": None, "gif_matrix": None, "rendered_at": None})


def mark_rendered(film_key: str, gif_web: str, gif_matrix: str) -> dict[str, Any]:
    """Called by the renderer (scripts/film_gif_render.py). Paths are relative to the data dir."""
    row = get(film_key)
    if row["status"] not in ("approved", "rendered"):
        raise CatalogError(f"{film_key} is {row['status']}, not approved", status=409)
    return _write({**row, "status": "rendered", "gif_web": gif_web, "gif_matrix": gif_matrix,
                   "rendered_at": timestamp()})
