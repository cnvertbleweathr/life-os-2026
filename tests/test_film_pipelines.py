"""
Offline tests for the film pipelines (no network, no warehouse writes).

  uv run --with pytest pytest tests/test_film_pipelines.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import letterboxd_pipeline as lb  # noqa: E402
from pipelines import plex_pipeline as px  # noqa: E402

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:letterboxd="https://letterboxd.com" xmlns:tmdb="https://themoviedb.org"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <item>
    <title>The Texas Chain Saw Massacre, 1974 - ★★★★★</title>
    <link>https://letterboxd.com/u/film/the-texas-chain-saw-massacre/</link>
    <guid isPermaLink="false">letterboxd-watch-1</guid>
    <pubDate>Sat, 31 Oct 2026 16:49:20 +1300</pubDate>
    <letterboxd:watchedDate>2026-10-30</letterboxd:watchedDate>
    <letterboxd:rewatch>No</letterboxd:rewatch>
    <letterboxd:filmTitle>The Texas Chain Saw Massacre</letterboxd:filmTitle>
    <letterboxd:filmYear>1974</letterboxd:filmYear>
    <letterboxd:memberRating>5.0</letterboxd:memberRating>
    <letterboxd:memberLike>Yes</letterboxd:memberLike>
    <tmdb:movieId>30497</tmdb:movieId>
    <description><![CDATA[<p><img src="x.jpg"/></p><p>Watched on Friday October 30, 2026.</p>]]></description>
  </item>
  <item>
    <title>Idle Hands, 1999 - ★★★★</title>
    <link>https://letterboxd.com/u/film/idle-hands/</link>
    <guid isPermaLink="false">letterboxd-review-2</guid>
    <letterboxd:watchedDate>2026-10-21</letterboxd:watchedDate>
    <letterboxd:rewatch>Yes</letterboxd:rewatch>
    <tmdb:movieId>6552</tmdb:movieId>
    <description><![CDATA[<p><img src="y.jpg"/></p><p>Need more stoner horror.</p>]]></description>
  </item>
  <item>
    <title>Halloween list</title>
    <link>https://letterboxd.com/u/list/halloween/</link>
    <guid isPermaLink="false">letterboxd-list-3</guid>
  </item>
</channel>
</rss>"""


def test_letterboxd_parse_feed_reads_tmdb_and_skips_lists():
    rows = lb.parse_feed(FEED, "u")
    assert [r["entry_id"] for r in rows] == ["letterboxd-watch-1", "letterboxd-review-2"]

    tcsm, idle = rows
    assert tcsm["tmdb_id"] == 30497
    assert tcsm["film_title"] == "The Texas Chain Saw Massacre"
    assert tcsm["film_year"] == 1974
    assert tcsm["watched_date"] == "2026-10-30"
    assert tcsm["rating"] == 5.0
    assert tcsm["liked"] is True and tcsm["is_rewatch"] is False
    assert tcsm["review"] is None   # poster + "Watched on…" only

    # No namespaced title/year/rating: falls back to parsing the <title>.
    assert idle["film_title"] == "Idle Hands" and idle["film_year"] == 1999
    assert idle["rating"] == 4.0
    assert idle["entry_type"] == "review" and idle["is_rewatch"] is True
    assert idle["review"] == "Need more stoner horror."


def test_plex_tmdb_id_from_guids():
    assert px.tmdb_id_from_guids({"Guid": [{"id": "imdb://tt0072271"}, {"id": "tmdb://30497"}]}) == 30497
    assert px.tmdb_id_from_guids({"guid": "com.plexapp.agents.themoviedb://30497?lang=en"}) == 30497
    assert px.tmdb_id_from_guids({"guid": "plex://movie/abc", "Guid": []}) is None
    assert px.tmdb_id_from_guids(None) is None


def test_plex_to_row_uses_denver_day():
    # 2026-10-31 03:00 UTC is still the evening of Oct 30 in Denver.
    item = {"historyKey": "/status/sessions/history/9", "ratingKey": "42", "title": "TCSM",
            "type": "movie", "viewedAt": 1793415600, "accountID": 1}
    meta = {"title": "The Texas Chain Saw Massacre", "year": 1974, "duration": 4980000,
            "Guid": [{"id": "tmdb://30497"}], "Media": [{"Part": [{"file": "/m/tcsm.mkv"}]}]}
    row = px.to_row(item, meta)
    assert row["watched_date"] == "2026-10-30"
    assert row["tmdb_id"] == 30497 and row["film_year"] == 1974
    assert row["file_path"] == "/m/tcsm.mkv" and row["in_library"] is True

    gone = px.to_row({**item, "originallyAvailableAt": "1974-10-11"}, None)
    assert gone["tmdb_id"] is None and gone["in_library"] is False
    assert gone["title"] == "TCSM" and gone["film_year"] == 1974


class FakeClient(px.PlexClient):
    """History pages + metadata from memory; counts metadata lookups."""

    def __init__(self, history, metadata):
        self._history, self._metadata, self.lookups = history, metadata, 0

    def get(self, path, params=None):
        if path == "/status/sessions/history/all":
            start, size = params["X-Plex-Container-Start"], params["X-Plex-Container-Size"]
            return {"Metadata": self._history[start:start + size]}
        raise AssertionError(path)

    def metadata(self, rating_key):
        self.lookups += 1
        return self._metadata.get(rating_key)


def test_plex_movie_rows_filters_movies_stops_at_cursor_and_caches_lookups(monkeypatch):
    monkeypatch.setattr(px, "PAGE_SIZE", 2)
    history = [   # newest first, as the server returns it
        {"historyKey": "a", "ratingKey": "1", "type": "movie", "viewedAt": 500},
        {"historyKey": "b", "ratingKey": "9", "type": "episode", "viewedAt": 400},
        {"historyKey": "c", "ratingKey": "1", "type": "movie", "viewedAt": 300},
        {"historyKey": "d", "ratingKey": "2", "type": "movie", "viewedAt": 100},
    ]
    client = FakeClient(history, {"1": {"Guid": [{"id": "tmdb://348"}]}})

    rows = list(px.movie_rows(client, None, since=200))
    assert [r["history_key"] for r in rows] == ["a", "c"]   # episode dropped, d is before the cursor
    assert [r["tmdb_id"] for r in rows] == [348, 348]
    assert client.lookups == 1


def test_plex_without_config_exits_zero(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "PLEX_URL": "", "PLEX_TOKEN": "",
           "ONS_DUCKDB_PATH": str(tmp_path / "ons.duckdb")}
    proc = subprocess.run([sys.executable, str(ROOT / "pipelines/plex_pipeline.py")],
                          env=env, capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "skipping" in proc.stdout
    assert not (tmp_path / "ons.duckdb").exists()
