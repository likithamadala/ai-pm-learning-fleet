"""Scout — daily digest logic.

Deterministic prep + commit around a single `claude -p` reasoning step (the scaffolding), so
the model only reasons. Run unattended by scripts/scout.ps1 on a schedule.

  prep   : pull feeds, dedup, rank by recency + relevance to your targets, extract the top-N,
           write the chosen set + a ready-to-send prompt for `claude -p`.
  commit : after the brief is written, mark the chosen URLs processed, log the run, bump streak.

CLI:
  python scripts/scout.py prep   --feeds sources/feeds.opml --top 2 --candidates 12
  python scripts/scout.py commit
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import extract  # sibling module (scripts/ is on sys.path when run as a script)
import ledger

ROOT = Path(__file__).resolve().parent.parent
CHOSEN_PATH = ledger.runs_dir() / "_scout_chosen.json"
PROMPT_PATH = ledger.runs_dir() / "_scout_prompt.txt"
MAX_TEXT = 4000  # chars of article text to hand the model per item

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "your", "you're", "from", "into", "what",
    "their", "they", "them", "role", "roles", "keywords", "target", "targets", "decoder",
    "reads", "matters", "framing", "split", "lives", "ledger", "across", "first", "both",
    "appear", "using", "tools", "rapidly", "building", "direct", "proof", "raw", "extract",
    "local", "ignored", "source", "sources",
}


def relevance_terms(jd_keywords_md: str) -> set[str]:
    """Distinct lowercase content words from the target-JD keywords, for relevance scoring."""
    words = re.findall(r"[a-zA-Z][a-zA-Z/+-]{3,}", jd_keywords_md.lower())
    return {w for w in words if w not in _STOPWORDS}


def score(item: dict, terms: set[str]) -> tuple[int, float]:
    """Rank key: (relevance hits, recency). Higher is better on both."""
    hay = f"{item.get('title','')} {item.get('summary','')}".lower()
    hits = sum(1 for t in terms if t in hay)
    return (hits, item.get("published_ts") or 0)


def select_candidates(items: list[dict], jd_keywords_md: str, top_n: int) -> list[dict]:
    terms = relevance_terms(jd_keywords_md)
    ranked = sorted(items, key=lambda it: score(it, terms), reverse=True)
    return ranked[:top_n]


def build_prompt(chosen: list[dict], context: dict) -> str:
    known = ", ".join(context.get("known_concepts", [])) or "(none yet)"
    fb = context.get("recent_feedback", [])
    last_depth = fb[-1]["depth"] if fb else "none"
    parts = [
        "Produce today's learning brief from the candidate articles below.",
        f"Concepts the reader already knows (do NOT re-explain): {known}.",
        f"Most recent depth feedback: {last_depth} "
        "(too_shallow → go deeper/assume more; too_deep → simplify and define more).",
        "",
        "Candidate articles:",
    ]
    for i, item in enumerate(chosen, 1):
        body = (item.get("text") or item.get("summary") or "").strip()[:MAX_TEXT]
        parts.append(f"\n[{i}] {item.get('title','(untitled)')}\nURL: {item.get('url','')}\n{body}")
    return "\n".join(parts)


def _prep(feeds_path: str, top_n: int, candidates: int) -> int:
    feed_urls = extract.read_opml(feeds_path)
    pool = extract.fetch_feeds(feed_urls, is_processed=ledger.is_processed, top_n=candidates)
    if not pool:
        print(json.dumps({"chosen": 0, "reason": "no new items"}))
        return 3  # nothing to brief today
    chosen = select_candidates(pool, ledger.read_jd_keywords(), top_n)
    for item in chosen:  # attach full text where we can; degrade to the feed summary otherwise
        result = extract.extract(item["url"])
        item["text"] = result["text"] if result["ok"] else ""
    ledger.runs_dir().mkdir(parents=True, exist_ok=True)
    CHOSEN_PATH.write_text(json.dumps(chosen, ensure_ascii=False), encoding="utf-8")
    PROMPT_PATH.write_text(build_prompt(chosen, ledger.context()), encoding="utf-8")
    print(json.dumps({"chosen": len(chosen), "urls": [c["url"] for c in chosen],
                      "prompt_file": str(PROMPT_PATH)}, ensure_ascii=False))
    return 0


def _commit() -> int:
    if not CHOSEN_PATH.exists():
        print(json.dumps({"committed": 0, "reason": "no chosen set"}))
        return 0
    chosen = json.loads(CHOSEN_PATH.read_text(encoding="utf-8"))
    urls = [c["url"] for c in chosen]
    for u in urls:
        ledger.mark_processed(u, agent="scout")
    ledger.log_run("scout:daily", urls, agent="scout")
    streak = ledger.bump_streak()
    CHOSEN_PATH.unlink(missing_ok=True)
    PROMPT_PATH.unlink(missing_ok=True)
    print(json.dumps({"committed": len(urls), "streak": streak["current_streak"]}))
    return 0


def _main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Scout daily digest logic")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prep")
    pp.add_argument("--feeds", default=str(ROOT / "sources" / "feeds.opml"))
    pp.add_argument("--top", type=int, default=2)
    pp.add_argument("--candidates", type=int, default=12)
    sub.add_parser("commit")
    args = p.parse_args(argv)
    if args.cmd == "prep":
        return _prep(args.feeds, args.top, args.candidates)
    return _commit()


if __name__ == "__main__":
    raise SystemExit(_main())
