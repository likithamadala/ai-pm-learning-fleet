import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cartographer  # noqa: E402
import ledger  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AILF_LEDGER_DIR", str(tmp_path / "ledger"))
    (tmp_path / "ledger").mkdir()
    yield


def _seed_small():
    # tokens (known) -> embeddings (tier1) -> rag (tier3)
    ledger.upsert_map_concept("tokens", "Tokens", 0, [], "general", "units of text")
    ledger.upsert_concept("Tokens", comprehension=2)  # mark known (encountered)
    ledger.upsert_map_concept("embeddings", "Embeddings", 1, ["tokens"], "both", "meaning as vectors")
    ledger.upsert_map_concept("rag", "RAG", 3, ["embeddings"], "role_a", "ground answers in docs")


def test_ready_gates_on_prereqs():
    _seed_small()
    ready_ids = [r["id"] for r in cartographer.ready_targets()]
    assert "embeddings" in ready_ids       # prereq tokens is known (>=1)
    assert "rag" not in ready_ids          # prereq embeddings still unencountered
    assert "tokens" not in ready_ids       # already understood (>=2), not a target


def test_unlock_after_prereq_seen():
    _seed_small()
    ledger.upsert_concept("Embeddings", comprehension=1)  # now "seen"
    ready_ids = [r["id"] for r in cartographer.ready_targets()]
    assert "rag" in ready_ids              # embeddings>=1 unlocks rag
    # tier order: embeddings (1) ranks before rag (3)
    assert ready_ids.index("embeddings") < ready_ids.index("rag")


def test_next_includes_why_with_dependents():
    _seed_small()
    nxt = cartographer.next_concepts(1)
    assert nxt[0]["id"] == "embeddings"
    assert "unlocks" in nxt[0]["why"] and "RAG" in nxt[0]["why"]


def test_jd_weight_breaks_ties_within_tier():
    ledger.upsert_concept("LLMs", comprehension=2)
    ledger.upsert_map_concept("llms", "LLMs", 0, [], "general", "")
    ledger.upsert_map_concept("a-general", "A general", 1, ["llms"], "general", "")
    ledger.upsert_map_concept("b-both", "B both", 1, ["llms"], "both", "")
    ready_ids = [r["id"] for r in cartographer.ready_targets()]
    assert ready_ids.index("b-both") < ready_ids.index("a-general")  # 'both' outranks 'general'


def test_seed_preserves_learning_state():
    ledger.upsert_concept("Embeddings", comprehension=2)         # user already understands it
    ledger.upsert_map_concept("embeddings", "Embeddings", 1, ["tokens"], "both", "x")  # map refresh
    rec = next(r for r in ledger.read_concepts() if r["id"] == "embeddings")
    assert rec["comprehension"] == 2        # learning state untouched
    assert rec["tier"] == 1                  # map metadata applied


def test_seed_from_file(tmp_path):
    curric = tmp_path / "c.json"
    curric.write_text(json.dumps({"concepts": [
        {"id": "tokens", "term": "Tokens", "tier": 0, "prereqs": [], "jd": "general", "description": "d"},
        {"id": "embeddings", "term": "Embeddings", "tier": 1, "prereqs": ["tokens"], "jd": "both", "description": "d"},
    ]}), encoding="utf-8")
    n = cartographer.seed(str(curric))
    assert n == 2
    ids = {r["id"] for r in ledger.read_concepts()}
    assert {"tokens", "embeddings"} <= ids


def test_pointer_and_map_render():
    _seed_small()
    assert "Next on your map" in cartographer.pointer()
    m = cartographer.map_view()
    assert "Tier 1" in m and "Embeddings" in m and "Progress:" in m
