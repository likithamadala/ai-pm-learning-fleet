import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import scout  # noqa: E402


def test_relevance_terms_drops_stopwords_and_short_words():
    terms = scout.relevance_terms("Embeddings and RAG for the target role; data-driven")
    assert "embeddings" in terms
    assert "data-driven" in terms
    assert "the" not in terms and "for" not in terms
    assert "and" not in terms


def test_select_ranks_relevance_over_recency():
    jd = "embeddings rag vector search"
    items = [
        {"title": "Cooking pasta", "summary": "nothing technical", "url": "a", "published_ts": 999},
        {"title": "Intro to RAG", "summary": "embeddings and vector search", "url": "b", "published_ts": 1},
    ]
    chosen = scout.select_candidates(items, jd, top_n=1)
    assert chosen[0]["url"] == "b"  # relevant-but-older beats recent-but-irrelevant


def test_select_breaks_ties_by_recency():
    jd = "embeddings"
    items = [
        {"title": "Embeddings A", "summary": "embeddings", "url": "old", "published_ts": 10},
        {"title": "Embeddings B", "summary": "embeddings", "url": "new", "published_ts": 20},
    ]
    chosen = scout.select_candidates(items, jd, top_n=1)
    assert chosen[0]["url"] == "new"  # equal relevance -> newer wins


def test_build_prompt_includes_known_concepts_and_urls():
    chosen = [{"title": "T1", "url": "https://x/1", "summary": "s", "text": "body one"}]
    context = {"known_concepts": ["LLMs", "Tokens"], "recent_feedback": [{"depth": "too_shallow"}]}
    prompt = scout.build_prompt(chosen, context)
    assert "LLMs, Tokens" in prompt
    assert "do NOT re-explain" in prompt
    assert "too_shallow" in prompt
    assert "https://x/1" in prompt
    assert "body one" in prompt
