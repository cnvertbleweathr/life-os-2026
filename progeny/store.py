"""
progeny/store.py — config, reference data and the append-only write path for Progeny.

Privacy: everything about the kids lives in data/progeny/ (gitignored). Only the
generic reference YAML in progeny/reference/ and the template in progeny/config/
are committed.

Write path: the web page's forms (POST /api/progeny/<kind>, api/routers/progeny.py)
call append_entry(), which appends one line to
data/progeny/<kind>.jsonl through api.store.JsonlLog (file lock + fsync). Nothing
here writes to DuckDB; the daily sync loads the logs with
pipelines/progeny_pipeline.py.

Every entry carries a uuid `id`. To edit an entry, append a full copy with the
same id; to delete one, append {"id": ..., "deleted": true}. The latest line per
id wins (same convention as the other ONS logs).
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from api.store import JsonlLog, data_dir, timestamp, today_local

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "progeny" / "reference"
MILESTONES_YAML = REFERENCE_DIR / "cdc_milestones.yaml"
PATHS_YAML = REFERENCE_DIR / "learning_paths.yaml"

SUBDIR = "progeny"

# kind → required fields (beyond id/logged_at), optional fields, date fields
KINDS: dict[str, dict[str, tuple[str, ...]]] = {
    "quotes":        {"required": ("kid", "date", "quote"),          "optional": ("context",),
                      "dates": ("date",)},
    "firsts":        {"required": ("kid", "date", "title"),          "optional": ("notes",),
                      "dates": ("date",)},
    "books":         {"required": ("kid", "date", "title"),          "optional": ("author", "repeat"),
                      "dates": ("date",)},
    "milestones":    {"required": ("kid", "milestone_id", "observed_date"), "optional": ("notes",),
                      "dates": ("observed_date",)},
    "path_evidence": {"required": ("kid", "path", "level", "date"),  "optional": ("notes",),
                      "dates": ("date",)},
    "prep_tasks":    {"required": ("task",), "optional": ("category", "due_date", "done_date", "created_date"),
                      "dates": ("due_date", "done_date", "created_date")},
}

LOGS = {kind: JsonlLog(SUBDIR, f"{kind}.jsonl") for kind in KINDS}

DOMAIN_KEYS = ("social_emotional", "language", "cognitive", "movement")


# ── config ────────────────────────────────────────────────────────────────────

def progeny_dir() -> Path:
    return data_dir() / SUBDIR


def kids_path() -> Path:
    return progeny_dir() / "kids.yaml"


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def load_kids() -> list[dict[str, Any]]:
    """Kids from data/progeny/kids.yaml, or [] if it doesn't exist yet."""
    path = kids_path()
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kids = []
    seen: set[str] = set()
    for raw in doc.get("kids") or []:
        kid_id = str(raw.get("kid_id") or "").strip()
        if not kid_id:
            raise ValueError(f"{path}: every kid needs a kid_id")
        if kid_id in seen:
            raise ValueError(f"{path}: duplicate kid_id {kid_id!r}")
        seen.add(kid_id)
        kid = {
            "kid_id": kid_id,
            "display_name": str(raw.get("display_name") or kid_id),
            "birthdate": _iso(raw.get("birthdate")),
            "due_date": _iso(raw.get("due_date")),
            "kindergarten_start": _iso(raw.get("kindergarten_start")),
        }
        if not kid["birthdate"] and not kid["due_date"]:
            raise ValueError(f"{path}: {kid_id} needs a birthdate or a due_date")
        kids.append(kid)
    return kids


# ── reference ─────────────────────────────────────────────────────────────────

def milestone_rows() -> list[dict[str, Any]]:
    """Flatten cdc_milestones.yaml to one row per milestone with a stable id."""
    doc = yaml.safe_load(MILESTONES_YAML.read_text(encoding="utf-8"))
    domain_labels = doc["domains"]
    rows = []
    for band in doc["bands"]:
        months = int(band["months"])
        for domain in DOMAIN_KEYS:
            for i, text in enumerate(band["milestones"].get(domain) or [], start=1):
                rows.append({
                    "milestone_id": f"cdc_{months}m_{domain}_{i:02d}",
                    "band_months": months,
                    "band_label": band["label"],
                    "domain": domain,
                    "domain_label": domain_labels[domain],
                    "sort_order": i,
                    "milestone": str(text),
                    "source_url": band.get("url"),
                })
    return rows


def learning_paths() -> list[dict[str, Any]]:
    return yaml.safe_load(PATHS_YAML.read_text(encoding="utf-8"))["paths"]


def path_level_rows() -> list[dict[str, Any]]:
    """Flatten learning_paths.yaml to one row per (path, level)."""
    rows = []
    for p_order, path in enumerate(learning_paths(), start=1):
        levels = path["levels"]
        for n, level in enumerate(levels, start=1):
            rows.append({
                "path_key": path["key"],
                "path_name": path["name"],
                "path_order": p_order,
                "min_age_months": int(path.get("min_age_months", 0)),
                "level_num": n,
                "total_levels": len(levels),
                "level_key": level["key"],
                "level_name": level["name"],
                "description": level.get("description", ""),
                # Newline-joined so DLT keeps it as one text column
                "activities": "\n".join(level.get("activities") or []),
            })
    return rows


# ── write path ────────────────────────────────────────────────────────────────

def _validate(kind: str, rec: dict[str, Any]) -> None:
    spec = KINDS[kind]
    missing = [f for f in spec["required"] if rec.get(f) in (None, "")]
    if missing:
        raise ValueError(f"{kind}: missing {', '.join(missing)}")
    for f in spec["dates"]:
        if rec.get(f) not in (None, ""):
            rec[f] = _iso(rec[f])
    if "kid" in spec["required"]:
        kid_ids = {k["kid_id"] for k in load_kids()}
        if rec["kid"] not in kid_ids:
            raise ValueError(f"{kind}: unknown kid {rec['kid']!r} (add it to {kids_path()})")
    if kind == "milestones":
        if rec["milestone_id"] not in {m["milestone_id"] for m in milestone_rows()}:
            raise ValueError(f"unknown milestone_id {rec['milestone_id']!r}")
    if kind == "path_evidence":
        levels = {(r["path_key"], r["level_key"]) for r in path_level_rows()}
        if (rec["path"], rec["level"]) not in levels:
            raise ValueError(f"unknown path/level {rec['path']}/{rec['level']}")
    if kind == "books":
        rec["repeat"] = bool(rec.get("repeat", False))


def append_entry(kind: str, fields: dict[str, Any], entry_id: str | None = None,
                 source: str = "web") -> dict[str, Any]:
    """Validate and append one entry. Pass entry_id to edit an existing entry."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    spec = KINDS[kind]
    allowed = set(spec["required"]) | set(spec["optional"])
    rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items() if k in allowed}
    if kind == "prep_tasks" and not rec.get("created_date"):
        rec["created_date"] = today_local().isoformat()
    _validate(kind, rec)
    record = {"id": entry_id or str(uuid.uuid4()), **rec,
              "deleted": False, "logged_at": timestamp(), "source": source}
    return LOGS[kind].append(record)


def delete_entry(kind: str, entry_id: str) -> dict[str, Any]:
    return LOGS[kind].append({"id": entry_id, "deleted": True, "logged_at": timestamp()})


def latest_entries(kind: str) -> list[dict[str, Any]]:
    """Latest row per id, deletions included (the pipeline loads tombstones too)."""
    return list(LOGS[kind].latest_by("id").values())
