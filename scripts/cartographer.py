"""Cartographer - the concept map / curriculum.

Maintains a model of the whole AI-concept space a PM targeting the user's roles should know,
seeded from sources/curriculum.json into the Ledger, and answers "what should I learn next?"

It maps and orders; it does not teach (Decoder/`/next` lesson teaches), retain (Drill), or
prove (Showcase). A concept is a *learning target* until comprehension >= 2 ("understood"), and
*ready* once all its prerequisites are at comprehension >= 1 ("seen").

CLI:
  python scripts/cartographer.py seed [--file sources/curriculum.json]   # seed/refresh the map
  python scripts/cartographer.py next [--n 1]                            # next ready target(s) as JSON
  python scripts/cartographer.py pointer                                 # one-line nudge (Scout footer)
  python scripts/cartographer.py map                                     # the roadmap with statuses
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import ledger

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CURRICULUM = ROOT / "sources" / "curriculum.json"

UNDERSTOOD = 2  # comprehension at/above this = no longer a learning target
SEEN = 1        # a prereq at/above this is "satisfied"
_JD_WEIGHT = {"both": 2, "role_a": 1, "role_b": 1, "general": 0}
_STATUS = {None: "[ ] new", 0: "[~] weak", 1: "[~] seen", 2: "[x] understood", 3: "[*] known"}


def _comp(rec: dict) -> int:
    return int(rec.get("comprehension") or 0)


def load_curriculum(path=DEFAULT_CURRICULUM) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["concepts"]


def seed(path=DEFAULT_CURRICULUM) -> int:
    concepts = load_curriculum(path)
    for c in concepts:
        ledger.upsert_map_concept(c["id"], c["term"], c["tier"], c.get("prereqs", []),
                                  c.get("jd", "general"), c.get("description", ""))
    return len(concepts)


def _mapped() -> list[dict]:
    """Concept records that are part of the map (have a tier)."""
    return [r for r in ledger.all_concepts_with_meta() if r.get("tier") is not None]


def ready_targets() -> list[dict]:
    """Learning targets (comprehension < 2) whose prereqs are all at >= 1, best-first."""
    by_id = {r["id"]: r for r in ledger.all_concepts_with_meta()}

    def prereqs_met(rec: dict) -> bool:
        for pid in rec.get("prereqs", []):
            p = by_id.get(pid)
            if p is None or _comp(p) < SEEN:
                return False
        return True

    targets = [r for r in _mapped() if _comp(r) < UNDERSTOOD]  # None/0/1 are targets; 2/3 are not
    ready = [r for r in targets if prereqs_met(r)]
    ready.sort(key=lambda r: (r.get("tier", 99), -_JD_WEIGHT.get(r.get("jd", "general"), 0), _comp(r)))
    return ready


def dependents(concept_id: str) -> list[str]:
    return [r["term"] for r in _mapped() if concept_id in r.get("prereqs", [])]


def next_concepts(n: int = 1) -> list[dict]:
    out = []
    for r in ready_targets()[:n]:
        deps = dependents(r["id"])
        why = f"tier {r.get('tier')} foundation"
        if deps:
            why += "; unlocks " + ", ".join(deps[:3])
        out.append({"id": r["id"], "term": r["term"], "description": r.get("description", ""),
                    "why": why, "comprehension": r.get("comprehension")})
    return out


def pointer() -> str:
    nxt = next_concepts(1)
    if not nxt:
        return "Next on your map: nothing ready - run /decode on something, or refresh the map."
    n = nxt[0]
    return f"Next on your map: {n['term']} ({n['why']}). Run /next to learn it."


def map_view() -> str:
    rows = sorted(_mapped(), key=lambda r: (r.get("tier", 99), r["term"].lower()))
    lines = ["# Concept map"]
    current = None
    for r in rows:
        if r.get("tier") != current:
            current = r.get("tier")
            lines.append(f"\n## Tier {current}")
        label = _STATUS.get(r.get("comprehension"), "[~] seen")
        lines.append(f"  {label}  {r['term']}")
    done = sum(1 for r in _mapped() if _comp(r) >= UNDERSTOOD)
    lines.append(f"\nProgress: {done}/{len(_mapped())} understood (>= level 2).")
    return "\n".join(lines)


def _main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Cartographer - concept map / curriculum")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed")
    sp.add_argument("--file", default=str(DEFAULT_CURRICULUM))
    np = sub.add_parser("next")
    np.add_argument("--n", type=int, default=1)
    sub.add_parser("pointer")
    sub.add_parser("map")
    args = p.parse_args(argv)

    if args.cmd == "seed":
        print(json.dumps({"seeded": seed(args.file)}))
    elif args.cmd == "next":
        print(json.dumps(next_concepts(args.n), ensure_ascii=False))
    elif args.cmd == "pointer":
        print(pointer())
    elif args.cmd == "map":
        print(map_view())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
