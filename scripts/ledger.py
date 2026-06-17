"""Knowledge Ledger helper.

The Ledger is the shared, self-correcting memory of what the user knows. Now that Scout runs
unattended (and can fire while the interactive Decoder is open), every read-modify-write takes a
**file lock** so concurrent writers can't lose each other's updates, plus atomic writes
(temp file + os.replace) so a crash can't truncate state.

Files (under ledger/):
  concepts.jsonl   {id, term, comprehension, last_seen, source, notes}
                   comprehension: 0=unknown 1=seen 2=understood 3=can-explain
  processed.jsonl  {url, date, agent}            (idempotency / de-dup)
  feedback.jsonl   {date, depth, note, context}  depth: too_shallow|just_right|too_deep
  streak.json      {last_brief_date, current_streak, longest_streak}

target_jd_keywords.md is free-form Markdown, read as text.

Usable as a library (import) and as a CLI (agents call it via the shell):
  python scripts/ledger.py context
  python scripts/ledger.py upsert --term "RAG" --comprehension 1 --source <url>
  python scripts/ledger.py is-processed --url <url>
  python scripts/ledger.py mark-processed --url <url> --agent scout
  python scripts/ledger.py feedback --depth just_right --note "..." --context <url>
  python scripts/ledger.py log-run --source <url> --concepts "RAG,embeddings"
  python scripts/ledger.py streak
  python scripts/ledger.py bump-streak
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

KNOWN_THRESHOLD = 2  # comprehension >= this means "don't re-explain"
_LOCK_ACQUIRE_TIMEOUT = 30.0  # max wait to acquire the ledger lock before giving up
_LOCK_STALE_AFTER = 60.0      # steal a lock older than this (left by a crashed holder)
_LOCK_POLL = 0.02


def ledger_dir() -> Path:
    """Resolve the ledger directory. Override with AILF_LEDGER_DIR (used by tests)."""
    override = os.environ.get("AILF_LEDGER_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "ledger"


def runs_dir() -> Path:
    override = os.environ.get("AILF_RUNS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "runs"


@contextmanager
def _file_lock():
    """Coarse cross-platform lock around any ledger mutation. Uses an exclusive lockfile
    (O_CREAT|O_EXCL) with a spin; steals a lock older than the timeout so a crashed writer
    can't deadlock the fleet."""
    lock_path = ledger_dir() / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    fd = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            # PermissionError happens on Windows when the prior holder's create/delete of the
            # same lockfile hasn't fully released — transient, so retry like a normal collision.
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue  # lock released between attempts; retry immediately
            if age > _LOCK_STALE_AFTER:
                lock_path.unlink(missing_ok=True)  # steal a crashed holder's lock
                continue
            if time.monotonic() - start > _LOCK_ACQUIRE_TIMEOUT:
                raise TimeoutError(f"could not acquire ledger lock at {lock_path}")
            time.sleep(_LOCK_POLL)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass  # another waiter may grab/recreate it; release is best-effort


def slugify(term: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", term.strip().lower()).strip("-")
    return s or "concept"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _atomic_write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.replace(tmp, path)  # atomic on the same filesystem (Windows + POSIX)
    except OSError:
        tmp.unlink(missing_ok=True)  # leave the original intact, drop the partial temp
        raise


def _today() -> str:
    return date.today().isoformat()


# --- concepts -------------------------------------------------------------

def read_concepts() -> list[dict]:
    return _read_jsonl(ledger_dir() / "concepts.jsonl")


def upsert_concept(term, comprehension=None, source=None, notes=None) -> dict:
    """Insert or update a concept by slug. comprehension only moves upward via upsert."""
    with _file_lock():
        rows = read_concepts()
        cid = slugify(term)
        existing = next((r for r in rows if r.get("id") == cid), None)
        if existing is None:
            rec = {
                "id": cid,
                "term": term.strip(),
                "comprehension": int(comprehension) if comprehension is not None else 1,
                "last_seen": _today(),
                "source": source or "decode",
                "notes": notes or "",
            }
            rows.append(rec)
        else:
            rec = existing
            if comprehension is not None:
                rec["comprehension"] = max(int(rec.get("comprehension") or 0), int(comprehension))
            rec["last_seen"] = _today()
            if source:
                rec["source"] = source
            if notes:
                rec["notes"] = notes
        _atomic_write_jsonl(ledger_dir() / "concepts.jsonl", rows)
        return rec


def upsert_map_concept(concept_id, term, tier, prereqs, jd, description) -> dict:
    """Seed/refresh a concept's map metadata (Cartographer). Creates an unencountered concept
    (comprehension=None) if new; on an existing concept, refreshes map metadata only and
    preserves all learning state (comprehension/box/next_due)."""
    meta = {"tier": tier, "prereqs": list(prereqs or []), "jd": jd, "description": description}
    with _file_lock():
        rows = read_concepts()
        rec = next((r for r in rows if r.get("id") == concept_id), None)
        if rec is None:
            rec = {"id": concept_id, "term": term, "comprehension": None,
                   "last_seen": None, "source": "cartographer", "notes": "", **meta}
            rows.append(rec)
        else:
            rec.update(meta)  # refresh map metadata; learning state untouched
            if not rec.get("term"):
                rec["term"] = term
        _atomic_write_jsonl(ledger_dir() / "concepts.jsonl", rows)
        return rec


def set_comprehension(term, level: int) -> dict | None:
    with _file_lock():
        rows = read_concepts()
        cid = slugify(term)
        rec = next((r for r in rows if r.get("id") == cid), None)
        if rec is None:
            return None
        rec["comprehension"] = int(level)
        rec["last_seen"] = _today()
        _atomic_write_jsonl(ledger_dir() / "concepts.jsonl", rows)
        return rec


def set_review_state(concept_id, box, next_due, comprehension) -> dict | None:
    """Persist a Drill review outcome: Leitner box, next due date, and comprehension."""
    with _file_lock():
        rows = read_concepts()
        rec = next((r for r in rows if r.get("id") == concept_id), None)
        if rec is None:
            return None
        rec["box"] = int(box)
        rec["next_due"] = next_due
        rec["comprehension"] = int(comprehension)
        rec["last_seen"] = _today()
        _atomic_write_jsonl(ledger_dir() / "concepts.jsonl", rows)
        return rec


def known_concepts(min_level: int = KNOWN_THRESHOLD) -> list[str]:
    """Terms the user already understands — callers skip re-explaining these (R3)."""
    return [r["term"] for r in read_concepts() if int(r.get("comprehension") or 0) >= min_level]


def all_concepts_with_meta() -> list[dict]:
    """Full concept records (including map metadata) for Cartographer queries."""
    return read_concepts()


# --- processed (idempotency) ---------------------------------------------

def is_processed(url: str) -> bool:
    return any(r.get("url") == url for r in _read_jsonl(ledger_dir() / "processed.jsonl"))


def mark_processed(url: str, agent: str = "decoder") -> None:
    with _file_lock():
        path = ledger_dir() / "processed.jsonl"
        rows = _read_jsonl(path)
        if not any(r.get("url") == url for r in rows):
            rows.append({"url": url, "date": _today(), "agent": agent})
            _atomic_write_jsonl(path, rows)


# --- feedback (the self-learning signal) ---------------------------------

VALID_DEPTHS = {"too_shallow", "just_right", "too_deep"}


def append_feedback(depth: str, note: str = "", context: str = "") -> dict:
    if depth not in VALID_DEPTHS:
        raise ValueError(f"depth must be one of {sorted(VALID_DEPTHS)}, got {depth!r}")
    with _file_lock():
        path = ledger_dir() / "feedback.jsonl"
        rows = _read_jsonl(path)
        rec = {"date": _today(), "depth": depth, "note": note, "context": context}
        rows.append(rec)
        _atomic_write_jsonl(path, rows)
        return rec


def recent_feedback(limit: int = 5) -> list[dict]:
    rows = _read_jsonl(ledger_dir() / "feedback.jsonl")
    return rows[-limit:]


# --- streak (R10) ---------------------------------------------------------

def read_streak() -> dict:
    path = ledger_dir() / "streak.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_brief_date": None, "current_streak": 0, "longest_streak": 0}


def bump_streak(today: str | None = None) -> dict:
    """Record that a brief ran today. Consecutive day -> +1; gap -> reset to 1; same day -> no-op."""
    today = today or _today()
    with _file_lock():
        s = read_streak()
        last = s.get("last_brief_date")
        if last != today:
            if last:
                gap = (date.fromisoformat(today) - date.fromisoformat(last)).days
            else:
                gap = None
            s["current_streak"] = s.get("current_streak", 0) + 1 if gap == 1 else 1
            s["last_brief_date"] = today
            s["longest_streak"] = max(s.get("longest_streak", 0), s["current_streak"])
        path = ledger_dir() / "streak.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(s), encoding="utf-8")
        os.replace(tmp, path)
        return s


# --- jd keywords ----------------------------------------------------------

def read_jd_keywords() -> str:
    path = ledger_dir() / "target_jd_keywords.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- run record (lightweight trace for debugging) ------------------------

def log_run(source: str, concepts: list[str], agent: str = "decoder", extra: dict | None = None) -> None:
    rd = runs_dir()
    rd.mkdir(parents=True, exist_ok=True)
    path = rd / f"{_today()}.jsonl"
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "source": source,
        "concepts": concepts,
    }
    if extra:
        rec.update(extra)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --- context blob (what agents read at the start of every run) -----------

def context() -> dict:
    concepts = read_concepts()
    return {
        "is_empty": len(concepts) == 0,
        "known_concepts": known_concepts(),
        "all_concepts": [
            {"term": r["term"], "comprehension": r.get("comprehension", 0)} for r in concepts
        ],
        "recent_feedback": recent_feedback(),
        "streak": read_streak(),
        "jd_keywords": read_jd_keywords(),
    }


# --- CLI ------------------------------------------------------------------

def _main(argv=None) -> int:
    try:  # ensure UTF-8 output on Windows (default console code page mangles non-ASCII)
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Knowledge Ledger helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("context")
    sub.add_parser("streak")
    bs = sub.add_parser("bump-streak")
    bs.add_argument("--date", default=None)

    up = sub.add_parser("upsert")
    up.add_argument("--term", required=True)
    up.add_argument("--comprehension", type=int, default=None)
    up.add_argument("--source", default=None)
    up.add_argument("--notes", default=None)

    sc = sub.add_parser("set-comprehension")
    sc.add_argument("--term", required=True)
    sc.add_argument("--level", type=int, required=True)

    ip = sub.add_parser("is-processed")
    ip.add_argument("--url", required=True)

    mp = sub.add_parser("mark-processed")
    mp.add_argument("--url", required=True)
    mp.add_argument("--agent", default="decoder")

    fb = sub.add_parser("feedback")
    fb.add_argument("--depth", required=True, choices=sorted(VALID_DEPTHS))
    fb.add_argument("--note", default="")
    fb.add_argument("--context", default="")

    lr = sub.add_parser("log-run")
    lr.add_argument("--source", required=True)
    lr.add_argument("--concepts", default="")
    lr.add_argument("--agent", default="decoder")

    args = p.parse_args(argv)

    if args.cmd == "context":
        print(json.dumps(context(), ensure_ascii=False, indent=2))
    elif args.cmd == "streak":
        print(json.dumps(read_streak()))
    elif args.cmd == "bump-streak":
        print(json.dumps(bump_streak(args.date)))
    elif args.cmd == "upsert":
        print(json.dumps(upsert_concept(args.term, args.comprehension, args.source, args.notes)))
    elif args.cmd == "set-comprehension":
        rec = set_comprehension(args.term, args.level)
        print(json.dumps(rec) if rec else json.dumps({"error": "term not found"}))
    elif args.cmd == "is-processed":
        print(json.dumps({"url": args.url, "processed": is_processed(args.url)}))
    elif args.cmd == "mark-processed":
        mark_processed(args.url, args.agent)
        print(json.dumps({"url": args.url, "marked": True}))
    elif args.cmd == "feedback":
        print(json.dumps(append_feedback(args.depth, args.note, args.context)))
    elif args.cmd == "log-run":
        concepts = [c.strip() for c in args.concepts.split(",") if c.strip()]
        log_run(args.source, concepts, args.agent)
        print(json.dumps({"logged": True, "concepts": concepts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
