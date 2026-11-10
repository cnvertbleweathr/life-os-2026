"""
Progeny: write path, reference parsing, pipeline loads and the privacy guard.

Everything writes to a tmp ONS_DATA_DIR / ONS_DUCKDB_PATH. Sample kids are fake.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]

KIDS_YAML = """kids:
  - kid_id: kid1
    display_name: Sample Kid
    birthdate: 2022-06-01
  - kid_id: kid2
    display_name: Baby
    birthdate: null
    due_date: 2027-06-01
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.delenv("ONS_DEV", raising=False)
    return tmp_path


@pytest.fixture()
def kids(env):
    from progeny import store
    store.progeny_dir().mkdir(parents=True, exist_ok=True)
    store.kids_path().write_text(KIDS_YAML)
    return env


def _con(env):
    return duckdb.connect(str(env / "test.duckdb"), read_only=True)


# ── privacy ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "data/progeny/kids.yaml",
    "data/progeny/quotes.jsonl",
    "data/progeny/README.md",          # data/**/README.md is otherwise un-ignored
    "data/progeny/photos/first_day.jpg",
])
def test_progeny_data_is_gitignored(path):
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert r.returncode == 0, f"{path} is not gitignored"


def test_example_config_has_no_real_kid_data():
    import yaml
    doc = yaml.safe_load((ROOT / "progeny/config/kids.example.yaml").read_text())
    assert [k["display_name"] for k in doc["kids"]] == ["Older Kid", "Baby"]


# ── reference ────────────────────────────────────────────────────────────────

def test_milestone_ids_are_unique_and_stable():
    from progeny import store
    rows = store.milestone_rows()
    ids = [r["milestone_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert {r["band_months"] for r in rows} == {2, 4, 6, 9, 12, 15, 18, 24, 30, 36, 48, 60}
    assert "cdc_48m_language_01" in ids
    assert {r["domain"] for r in rows} == set(store.DOMAIN_KEYS)


def test_learning_paths_have_ordered_levels_with_activities():
    from progeny import store
    paths = store.learning_paths()
    assert {p["key"] for p in paths} == {
        "literacy", "numeracy", "fine_motor", "gross_motor", "social_emotional", "music", "practical_life"}
    for p in paths:
        keys = [lvl["key"] for lvl in p["levels"]]
        assert len(keys) == len(set(keys)) >= 3
        for lvl in p["levels"]:
            assert lvl["name"] and lvl["description"]
            assert 2 <= len(lvl["activities"]) <= 3


# ── write path ───────────────────────────────────────────────────────────────

def test_append_validates(kids):
    from progeny import store
    with pytest.raises(ValueError, match="unknown kid"):
        store.append_entry("quotes", {"kid": "nobody", "date": "2026-11-01", "quote": "hi"})
    with pytest.raises(ValueError, match="missing quote"):
        store.append_entry("quotes", {"kid": "kid1", "date": "2026-11-01", "quote": "  "})
    with pytest.raises(ValueError, match="milestone_id"):
        store.append_entry("milestones", {"kid": "kid1", "milestone_id": "x", "observed_date": "2026-11-01"})
    with pytest.raises(ValueError, match="path/level"):
        store.append_entry("path_evidence", {"kid": "kid1", "path": "literacy", "level": "x", "date": "2026-11-01"})
    with pytest.raises(ValueError):
        store.append_entry("firsts", {"kid": "kid1", "date": "yesterday", "title": "x"})


def test_append_writes_jsonl_with_uuid(kids):
    from progeny import store
    rec = store.append_entry("quotes", {"kid": "kid1", "date": "2026-11-01", "quote": "hi", "junk": 1})
    assert len(rec["id"]) == 36 and "junk" not in rec
    assert (kids / "data" / "progeny" / "quotes.jsonl").exists()


def test_missing_kids_yaml_means_no_kids(env):
    from progeny import store
    assert store.load_kids() == []


# ── pipeline ─────────────────────────────────────────────────────────────────

def test_pipeline_runs_on_empty(env):
    from pipelines import progeny_pipeline
    progeny_pipeline.run()
    con = _con(env)
    assert con.execute("SELECT count(*) FROM progeny.milestone_ref").fetchone()[0] > 100
    assert con.execute("SELECT count(*) FROM progeny.path_levels").fetchone()[0] > 30
    con.close()


def test_pipeline_merges_edits_and_tombstones(kids):
    from pipelines import progeny_pipeline
    from progeny import store

    q = store.append_entry("quotes", {"kid": "kid1", "date": "2026-11-01", "quote": "first draft"})
    store.append_entry("quotes", {"kid": "kid1", "date": "2026-11-01", "quote": "edited"}, entry_id=q["id"])
    gone = store.append_entry("quotes", {"kid": "kid1", "date": "2026-11-02", "quote": "typo"})
    store.delete_entry("quotes", gone["id"])
    store.append_entry("books", {"kid": "kid1", "date": "2026-11-01", "title": "Goodnight Moon"})
    t = store.append_entry("prep_tasks", {"task": "Car seat", "due_date": "2027-05-01"})
    store.append_entry("prep_tasks", {**{k: t[k] for k in ("task", "due_date", "created_date")},
                                      "done_date": "2026-11-03"}, entry_id=t["id"])

    progeny_pipeline.run()
    progeny_pipeline.run()  # merge must be idempotent

    con = _con(env=kids)
    assert con.execute(
        "SELECT quote FROM progeny.quotes WHERE NOT deleted").fetchall() == [("edited",)]
    assert con.execute("SELECT count(*) FROM progeny.quotes WHERE deleted").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM progeny.books").fetchone()[0] == 1
    assert str(con.execute("SELECT done_date FROM progeny.prep_tasks").fetchone()[0]) == "2026-11-03"
    assert con.execute(
        "SELECT kid_id, birthdate IS NULL FROM progeny.kids ORDER BY kid_id").fetchall() == [
        ("kid1", False), ("kid2", True)]
    con.close()
