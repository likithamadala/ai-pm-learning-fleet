"""Health check for the AI Learning Fleet (Day-1 slice).

Run: python scripts/doctor.py
Verifies the Ledger files exist and the Python dependencies import. Exits non-zero if
anything required is missing, so it can gate a run.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "ledger"

REQUIRED_LEDGER_FILES = [
    "concepts.jsonl",
    "processed.jsonl",
    "feedback.jsonl",
    "target_jd_keywords.md",
]

# (module, pip name) — extract.py needs these; ledger.py is stdlib-only.
OPTIONAL_DEPS = [("feedparser", "feedparser"), ("trafilatura", "trafilatura")]


def _scheduled_task_status() -> str | None:
    """Informational daily-task status on Windows (None elsewhere / if unavailable)."""
    if sys.platform != "win32":
        return None
    import subprocess

    for name in ("AILF-Conductor", "AILF-Scout"):
        try:
            out = subprocess.run(["schtasks", "/query", "/tn", name, "/fo", "list", "/v"],
                                 capture_output=True, text=True)
        except FileNotFoundError:
            return None
        if out.returncode == 0:
            fields = {}
            for line in out.stdout.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fields[k.strip()] = v.strip()
            return (f"Daily task '{name}' scheduled - next {fields.get('Next Run Time', '?')}; "
                    f"last {fields.get('Last Run Time', '?')} (result {fields.get('Last Result', '?')})")
    return "No daily task scheduled - run scripts/install-conductor-task.ps1"


def main() -> int:
    try:  # UTF-8 output on Windows (default console code page mangles non-ASCII)
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    problems: list[str] = []
    notes: list[str] = []

    for name in REQUIRED_LEDGER_FILES:
        path = LEDGER / name
        if path.exists():
            notes.append(f"ok   ledger/{name}")
        else:
            problems.append(f"MISSING ledger/{name} (run from project root, or recreate it)")

    for module, pip_name in OPTIONAL_DEPS:
        if importlib.util.find_spec(module) is not None:
            notes.append(f"ok   import {module}")
        else:
            problems.append(
                f"MISSING dependency '{module}' — run: pip install {pip_name} "
                "(needed for URL fetching; paste-text still works without it)"
            )

    sched = _scheduled_task_status()
    if sched:
        notes.append(f"info {sched}")  # informational only — does not affect exit code

    for line in notes:
        print(line)
    for line in problems:
        print(line)

    if problems:
        print(f"\ndoctor: {len(problems)} problem(s) found.")
        return 1
    print("\ndoctor: all good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
