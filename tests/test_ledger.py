import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AILF_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("AILF_RUNS_DIR", str(tmp_path / "runs"))
    (tmp_path / "ledger").mkdir()
    yield


def test_upsert_inserts_then_updates_in_place():
    ledger.upsert_concept("Retrieval Augmented Generation", comprehension=1)
    ledger.upsert_concept("Retrieval Augmented Generation", comprehension=2)
    rows = ledger.read_concepts()
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0]["comprehension"] == 2


def test_comprehension_only_moves_up_on_upsert():
    ledger.upsert_concept("Embeddings", comprehension=3)
    ledger.upsert_concept("Embeddings", comprehension=1)  # should not lower
    assert ledger.read_concepts()[0]["comprehension"] == 3


def test_known_concepts_excludes_below_threshold():
    ledger.upsert_concept("RAG", comprehension=2)        # known
    ledger.upsert_concept("Diffusion", comprehension=1)  # only seen
    known = ledger.known_concepts()
    assert "RAG" in known
    assert "Diffusion" not in known


def test_processed_dedup():
    url = "https://example.com/a"
    assert ledger.is_processed(url) is False
    ledger.mark_processed(url)
    ledger.mark_processed(url)  # idempotent
    assert ledger.is_processed(url) is True
    rows = ledger._read_jsonl(ledger.ledger_dir() / "processed.jsonl")
    assert len(rows) == 1


def test_feedback_append_and_read():
    ledger.append_feedback("just_right", note="good", context="https://x")
    ledger.append_feedback("too_deep", note="lost me on transformers")
    recent = ledger.recent_feedback()
    assert len(recent) == 2
    assert recent[-1]["depth"] == "too_deep"


def test_feedback_rejects_bad_depth():
    with pytest.raises(ValueError):
        ledger.append_feedback("meh")


def test_context_reports_empty_then_populated():
    assert ledger.context()["is_empty"] is True
    ledger.upsert_concept("Tokens", comprehension=2)
    ctx = ledger.context()
    assert ctx["is_empty"] is False
    assert "Tokens" in ctx["known_concepts"]


def test_atomic_write_preserves_original_on_failure(monkeypatch):
    ledger.upsert_concept("Stable", comprehension=2)
    before = (ledger.ledger_dir() / "concepts.jsonl").read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(ledger.os, "replace", boom)
    with pytest.raises(OSError):
        ledger.upsert_concept("Doomed", comprehension=1)

    after = (ledger.ledger_dir() / "concepts.jsonl").read_text(encoding="utf-8")
    assert after == before  # original intact, no truncation
    assert not (ledger.ledger_dir() / "concepts.jsonl.tmp").exists()  # partial temp cleaned up


def test_streak_consecutive_then_gap_resets():
    ledger.bump_streak("2026-06-01")
    s = ledger.bump_streak("2026-06-02")  # consecutive day
    assert s["current_streak"] == 2
    s = ledger.bump_streak("2026-06-05")  # 3-day gap -> reset
    assert s["current_streak"] == 1
    assert s["longest_streak"] == 2


def test_streak_same_day_is_noop():
    ledger.bump_streak("2026-06-01")
    s = ledger.bump_streak("2026-06-01")
    assert s["current_streak"] == 1


def test_context_includes_streak():
    ledger.bump_streak("2026-06-01")
    assert ledger.context()["streak"]["current_streak"] == 1


def test_concurrent_upserts_no_lost_update():
    import threading

    def add(i):
        ledger.upsert_concept(f"Concept {i}", comprehension=1, source="t")

    threads = [threading.Thread(target=add, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Without the lock, interleaved read-modify-write would drop most of these.
    assert len(ledger.read_concepts()) == 25
