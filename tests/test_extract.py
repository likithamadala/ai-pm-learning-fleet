import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import extract  # noqa: E402


def test_looks_like_url():
    assert extract.looks_like_url("https://example.com/x")
    assert extract.looks_like_url("HTTP://Example.com")
    assert not extract.looks_like_url("just some pasted text")
    assert not extract.looks_like_url("www.example.com")  # no scheme


def test_assess_threshold():
    ok, _ = extract.assess("x" * extract.MIN_TEXT_LEN)
    assert ok is True
    ok, reason = extract.assess("too short")
    assert ok is False
    assert "paste" in reason.lower()


def test_pasted_text_accepted_as_is_even_if_short():
    result = extract.extract("a short note the user deliberately pasted")
    assert result["ok"] is True
    assert result["source_type"] == "text"
    assert result["text"].startswith("a short note")


def test_pasted_long_text_roundtrips():
    body = "Large language models " * 100
    result = extract.extract(body)
    assert result["ok"] is True
    assert result["text"] == body


RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item><title>Newer post</title><link>https://ex.com/new</link><guid>https://ex.com/new</guid>
<pubDate>Tue, 10 Jun 2026 10:00:00 GMT</pubDate><description>about RAG</description></item>
<item><title>Older post</title><link>https://ex.com/old</link><guid>https://ex.com/old</guid>
<pubDate>Mon, 02 Jun 2026 10:00:00 GMT</pubDate><description>about tokens</description></item>
</channel></rss>"""


def test_entries_from_feed_parses_offline_string():
    entries = extract.entries_from_feed(RSS_FIXTURE)
    urls = [e["url"] for e in entries]
    assert "https://ex.com/new" in urls and "https://ex.com/old" in urls
    assert all(e["published_ts"] for e in entries)
    assert all(e["feed_title"] == "Test Feed" for e in entries)


def test_select_new_dedups_orders_and_limits():
    entries = [
        {"url": "a", "published_ts": 100},
        {"url": "b", "published_ts": 300},
        {"url": "c", "published_ts": 200},
    ]
    out = extract.select_new(entries, is_processed=lambda u: u == "a", top_n=2)
    assert [e["url"] for e in out] == ["b", "c"]  # 'a' filtered, newest-first, capped at 2


def test_select_new_skips_urlless_entries():
    out = extract.select_new([{"url": None, "published_ts": 1}, {"url": "x", "published_ts": 2}])
    assert [e["url"] for e in out] == ["x"]


def test_read_opml_flattens_nested_outlines(tmp_path):
    opml = tmp_path / "f.opml"
    opml.write_text(
        '<?xml version="1.0"?><opml><body>'
        '<outline text="A" xmlUrl="https://a.com/feed"/>'
        '<outline text="grp"><outline text="B" xmlUrl="https://b.com/rss"/></outline>'
        "</body></opml>",
        encoding="utf-8",
    )
    assert extract.read_opml(str(opml)) == ["https://a.com/feed", "https://b.com/rss"]
