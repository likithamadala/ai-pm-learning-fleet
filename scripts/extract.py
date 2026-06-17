"""Article + feed ingestion for the fleet.

Deterministic fetch + parse so the model only reasons. Three jobs:
  - extract a single article (URL -> text via trafilatura, or pasted text accepted as-is)
  - parse an OPML feed list
  - pull feed entries, dedup against already-processed URLs, return the freshest top-N

If a URL yields too little text (paywall / JS-heavy page), we report a paste-fallback so the
caller asks the user to paste the article text instead.

CLI:
  python scripts/extract.py --url https://example.com/post
  python scripts/extract.py --file article.txt
  echo "pasted text..." | python scripts/extract.py
  python scripts/extract.py --feeds sources/feeds.opml --top 2
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys

MIN_TEXT_LEN = 500  # below this from a URL = probably paywalled/JS -> paste fallback


# --- single-article extraction -------------------------------------------

def looks_like_url(s: str) -> bool:
    s = s.strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def assess(text: str) -> tuple[bool, str]:
    """Judge whether URL-extracted text is usable. Pasted text bypasses this."""
    if text and len(text.strip()) >= MIN_TEXT_LEN:
        return True, "ok"
    return (
        False,
        "extracted too little text (paywalled or JS-heavy page) — paste the article text instead",
    )


def extract_url(url: str) -> str:
    """Fetch + extract a URL to plain text. Lazy import so the module loads without trafilatura."""
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "trafilatura is not installed (pip install trafilatura). Paste the article text instead."
        ) from exc
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return ""
    return trafilatura.extract(downloaded, output_format="markdown") or ""


def extract(source: str) -> dict:
    """Return {ok, text, source_type, reason}. Pasted text is accepted as-is."""
    source = source.lstrip("﻿")  # strip a leading BOM (e.g. from piped stdin)
    if looks_like_url(source):
        text = extract_url(source)
        ok, reason = assess(text)
        return {"ok": ok, "text": text if ok else "", "source_type": "url", "reason": reason}
    return {"ok": True, "text": source, "source_type": "text", "reason": "pasted text accepted"}


# --- feed ingestion -------------------------------------------------------

def read_opml(path: str) -> list[str]:
    """Return all feed URLs (outline[@xmlUrl]) from an OPML file."""
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    return [o.get("xmlUrl") for o in tree.iter("outline") if o.get("xmlUrl")]


def entries_from_feed(source: str) -> list[dict]:
    """Parse one feed (URL, file path, or raw XML string) into normalized entries."""
    import feedparser

    parsed = feedparser.parse(source)
    feed_title = parsed.get("feed", {}).get("title", "") if hasattr(parsed, "get") else ""
    out: list[dict] = []
    for e in parsed.entries:
        pp = e.get("published_parsed") or e.get("updated_parsed")
        ts = calendar.timegm(pp) if pp else None
        out.append(
            {
                "url": e.get("link") or e.get("id"),
                "title": e.get("title", ""),
                "summary": (e.get("summary", "") or "")[:500],
                "published": e.get("published") or e.get("updated") or "",
                "published_ts": ts,
                "feed_title": feed_title,
            }
        )
    return out


def select_new(entries: list[dict], is_processed=None, top_n: int = 2) -> list[dict]:
    """Drop already-processed and url-less entries, sort newest-first, take top_n."""
    seen = is_processed or (lambda url: False)
    fresh = [e for e in entries if e.get("url") and not seen(e["url"])]
    fresh.sort(key=lambda e: e.get("published_ts") or 0, reverse=True)
    return fresh[:top_n]


def fetch_feeds(feed_sources: list[str], is_processed=None, top_n: int = 2) -> list[dict]:
    """Pull entries across all feeds, dedup, return the freshest top_n. One bad feed is skipped."""
    pool: list[dict] = []
    for src in feed_sources:
        try:
            pool.extend(entries_from_feed(src))
        except Exception:
            continue  # a single broken feed must not kill the run
    return select_new(pool, is_processed, top_n)


# --- CLI ------------------------------------------------------------------

def _main(argv=None) -> int:
    try:  # ensure UTF-8 output on Windows (default console code page mangles non-ASCII)
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Article + feed ingestion")
    p.add_argument("--url")
    p.add_argument("--file", help="read article text from a file")
    p.add_argument("--feeds", help="path to an OPML feed list; switches to feed-discovery mode")
    p.add_argument("--top", type=int, default=2, help="how many fresh feed items to return")
    args = p.parse_args(argv)

    if args.feeds:
        try:
            import ledger  # sibling module; scripts/ is on sys.path when run as a script
            is_processed = ledger.is_processed
        except Exception:
            is_processed = None
        items = fetch_feeds(read_opml(args.feeds), is_processed=is_processed, top_n=args.top)
        print(json.dumps(items, ensure_ascii=False))
        return 0

    if args.url:
        result = extract(args.url)
    elif args.file:
        result = extract(open(args.file, encoding="utf-8").read())
    else:
        result = extract(sys.stdin.read())

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(_main())
