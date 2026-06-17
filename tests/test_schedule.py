import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import schedule  # noqa: E402
import ledger  # noqa: E402

T = date(2026, 6, 17)


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AILF_LEDGER_DIR", str(tmp_path / "ledger"))
    (tmp_path / "ledger").mkdir()
    yield


# --- transition (pure) ---

def test_transition_correct_moves_up_and_pushes_due():
    box, due = schedule.transition(1, True, T)
    assert box == 2 and due == (T + timedelta(days=3)).isoformat()  # INTERVALS[2] = 3


def test_transition_wrong_resets_to_box1_tomorrow():
    box, due = schedule.transition(4, False, T)
    assert box == 1 and due == (T + timedelta(days=1)).isoformat()


def test_transition_caps_at_box5():
    assert schedule.transition(5, True, T)[0] == 5


def test_transition_none_box_starts_at_1():
    assert schedule.transition(None, True, T)[0] == 2  # None -> box 1, correct -> 2


# --- due selection ---

def test_due_gates_on_comprehension_and_date():
    ledger.upsert_concept("Seen new", comprehension=1)  # no next_due -> due now
    ledger.upsert_concept("Mastered", comprehension=3)  # not drillable
    ledger.upsert_concept("Future", comprehension=1)
    ledger.set_review_state("future", 2, (T + timedelta(days=5)).isoformat(), 1)
    ledger.upsert_concept("Overdue", comprehension=2)
    ledger.set_review_state("overdue", 1, (T - timedelta(days=1)).isoformat(), 2)

    due_ids = [r["id"] for r in schedule.due(T)]
    assert "seen-new" in due_ids
    assert "overdue" in due_ids
    assert "mastered" not in due_ids
    assert "future" not in due_ids


def test_due_sorted_weakest_first():
    ledger.upsert_concept("A", comprehension=2)
    ledger.upsert_concept("B", comprehension=1)
    ids = [r["id"] for r in schedule.due(T)]
    assert ids.index("b") < ids.index("a")  # comprehension 1 before 2


# --- review (updates ledger) ---

def test_review_correct_promotes():
    ledger.upsert_concept("RAG", comprehension=1)
    rec = schedule.review("rag", True, T)
    assert rec["comprehension"] == 2
    assert rec["box"] == 2
    assert rec["next_due"] == (T + timedelta(days=3)).isoformat()


def test_review_wrong_demotes_and_resets():
    ledger.upsert_concept("RAG", comprehension=2)
    ledger.set_review_state("rag", 3, T.isoformat(), 2)
    rec = schedule.review("rag", False, T)
    assert rec["box"] == 1
    assert rec["comprehension"] == 1
    assert rec["next_due"] == (T + timedelta(days=1)).isoformat()


def test_comprehension_floor_and_ceiling():
    ledger.upsert_concept("X", comprehension=1)
    assert schedule.review("x", False, T)["comprehension"] == 1  # floor at 1
    ledger.upsert_concept("Y", comprehension=2)
    assert schedule.review("y", True, T)["comprehension"] == 3   # ceiling at 3


def test_review_missing_returns_none():
    assert schedule.review("nope", True, T) is None


def test_summary():
    assert schedule.summary(T) == ""
    ledger.upsert_concept("Z", comprehension=1)
    assert "due for review" in schedule.summary(T)
