"""Drill - spaced-repetition scheduling (Leitner).

Concepts you've encountered (comprehension 1-2) cycle through Leitner boxes with expanding review
intervals. A correct recall moves a concept up a box and pushes its next review out; a miss sends
it back to box 1 for tomorrow. Comprehension rises on correct recall (1->2->3) and dips on a miss
(never below 1), so Drill is what promotes "seen" concepts to "understood"/"known".

  due     : concepts ready for review (drillable + next_due reached), weakest-first
  review  : record an outcome -> updates box, next_due, comprehension
  summary : one-line "N due" string for Scout's brief footer

CLI:
  python scripts/schedule.py due
  python scripts/schedule.py review --id <concept-id> --correct true|false
  python scripts/schedule.py summary
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

import ledger

INTERVALS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}  # box -> days until next review
DRILLABLE = (1, 2)  # comprehension levels that are reviewed (encountered, not yet mastered)


def _today() -> date:
    return date.today()


def transition(box, correct: bool, today: date | None = None) -> tuple[int, str]:
    """Leitner box move. Returns (new_box, next_due_iso)."""
    today = today or _today()
    box = int(box) if box else 1
    new_box = min(box + 1, 5) if correct else 1
    due = today + timedelta(days=INTERVALS[new_box])
    return new_box, due.isoformat()


def is_due(rec: dict, today: date | None = None) -> bool:
    today = today or _today()
    if rec.get("comprehension") not in DRILLABLE:
        return False
    nd = rec.get("next_due")
    return nd is None or date.fromisoformat(nd) <= today


def due(today: date | None = None) -> list[dict]:
    """Drillable, due concepts — weakest (lowest comprehension) and longest-overdue first."""
    items = [r for r in ledger.all_concepts_with_meta() if is_due(r, today)]
    items.sort(key=lambda r: (r.get("comprehension", 1), r.get("next_due") or ""))
    return items


def review(ident: str, correct: bool, today: date | None = None) -> dict | None:
    """Record an outcome for the concept (matched by id or by the slug of its term)."""
    today = today or _today()
    rows = ledger.read_concepts()
    rec = next((r for r in rows if r.get("id") == ident or r.get("id") == ledger.slugify(ident)), None)
    if rec is None:
        return None
    new_box, next_due = transition(rec.get("box"), correct, today)
    comp = rec.get("comprehension") or 1
    new_comp = min(comp + 1, 3) if correct else max(comp - 1, 1)
    return ledger.set_review_state(rec["id"], new_box, next_due, new_comp)


def summary(today: date | None = None) -> str:
    n = len(due(today))
    return f"{n} concept(s) due for review - run /drill" if n else ""


def _main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Drill - spaced-repetition scheduling")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    rv = sub.add_parser("review")
    rv.add_argument("--id", required=True)
    rv.add_argument("--correct", required=True, choices=["true", "false"])
    sub.add_parser("summary")
    args = p.parse_args(argv)

    if args.cmd == "due":
        items = [{"id": r["id"], "term": r["term"], "box": r.get("box"),
                  "comprehension": r.get("comprehension")} for r in due()]
        print(json.dumps(items, ensure_ascii=False))
    elif args.cmd == "review":
        rec = review(args.id, args.correct == "true")
        print(json.dumps(rec, ensure_ascii=False) if rec else json.dumps({"error": "concept not found"}))
    elif args.cmd == "summary":
        print(summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
