"""
Offline tests for the news pipeline (no network, no warehouse writes).

  uv run --with pytest pytest tests/test_news_pipeline.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import news_pipeline as news  # noqa: E402

FETCHED = "2026-11-21T12:00:00+00:00"

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Town Plants 10,000 Trees &amp; Cuts Summer Heat</title>
    <link>https://www.goodnewsnetwork.org/town-trees/?utm_source=rss&amp;utm_medium=rss</link>
    <pubDate>Fri, 20 Nov 2026 14:30:00 +0000</pubDate>
    <description><![CDATA[<p>Volunteers planted <b>10,000</b> trees.</p>
      <p>The post Town Plants Trees appeared first on Good News Network.</p>]]></description>
  </item>
  <item><title>No link, skipped</title></item>
</channel></rss>"""


def test_parse_rss_strips_html_tracking_and_wordpress_footer():
    rows = news.parse_rss(RSS, "Good News Network", "good_news", FETCHED)
    assert len(rows) == 1
    r = rows[0]
    assert r["title"] == "Town Plants 10,000 Trees & Cuts Summer Heat"
    assert r["summary"] == "Volunteers planted 10,000 trees."
    assert r["published_at"] == "2026-11-20T14:30:00+00:00"
    assert r["category"] == "good_news"
    # tracking params don't change the id
    assert r["article_id"] == news.article_id("https://www.goodnewsnetwork.org/town-trees")


def test_parse_newsapi_drops_removed_and_source_suffix():
    payload = {"status": "ok", "articles": [
        {"source": {"name": "Ars Technica"}, "title": "Star swallows neighbor - Ars Technica",
         "url": "https://arstechnica.com/star", "description": "A giant star.",
         "publishedAt": "2026-11-21T03:00:00Z"},
        {"source": {"name": "X"}, "title": "[Removed]", "url": "https://removed.com"},
    ]}
    rows = news.parse_newsapi(payload, "science", FETCHED)
    assert [r["title"] for r in rows] == ["Star swallows neighbor"]
    assert rows[0]["source"] == "Ars Technica"


def test_parse_newsapi_error_raises():
    try:
        news.parse_newsapi({"status": "error", "code": "rateLimited", "message": "slow down"}, "science", FETCHED)
    except RuntimeError as e:
        assert "rateLimited" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_summary_is_capped_at_word_boundary():
    text = news.clean_text("word " * 200)
    assert len(text) <= news.SUMMARY_MAX + 1
    assert text.endswith("…") and not text.endswith(" …")
