import json

import pytest

pytest.importorskip("helixdb", reason="install the helix-evaluation extra")

from experiments.helix_retrieval import (
    SearchHit,
    embed_texts,
    load_relations,
    local_hash_embedding,
    rank_of_target,
    reciprocal_rank_fusion,
    summarize,
)


def test_load_relations_preserves_recorded_structure(tmp_path):
    corpus = tmp_path / "pairs.jsonl"
    rows = [
        {
            "a": "same event described first",
            "b": "same event described second",
            "relation": "paraphrase",
            "why": "same payout deadbeef, compliance vs intake",
        },
        {
            "a": "policy did not reject",
            "b": "policy rejected",
            "relation": "contradiction",
            "why": "policy P2: cafe1234 approved vs fade5678 rejected",
        },
    ]
    corpus.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    relations = load_relations(corpus)

    assert relations[0].a_payout == relations[0].b_payout == "deadbeef"
    assert relations[1].policy == "P2"
    assert relations[1].a_outcome == "approved"
    assert relations[1].b_outcome == "rejected"


def test_rrf_rewards_candidates_seen_by_both_searches():
    vector = [
        SearchHit("vector-only", "v", 1),
        SearchHit("both", "shared", 2),
    ]
    bm25 = [
        SearchHit("bm25-only", "b", 1),
        SearchHit("both", "shared", 2),
    ]

    fused = reciprocal_rank_fusion(vector, bm25)

    assert fused[0].external_id == "both"
    assert rank_of_target(fused, "shared") == 1


def test_summary_counts_missing_targets_as_failures():
    result = summarize([1, 4, None, 11], (1, 5, 10))

    assert result["recall_at_1"] == 0.25
    assert result["recall_at_5"] == 0.5
    assert result["recall_at_10"] == 0.5
    assert result["not_found"] == 1


def test_local_hash_embedding_is_normalized_and_deterministic():
    first = local_hash_embedding("Policy P2 rejects this payout")
    second = local_hash_embedding("Policy P2 rejects this payout")

    assert first == second
    assert len(first) == 1024
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_external_embedding_requires_explicit_corpus_disclosure(tmp_path):
    with pytest.raises(ValueError, match="DashScope would receive the corpus"):
        embed_texts(
            ["recorded decision text"],
            tmp_path / "cache.json",
            provider="dashscope",
            allow_third_party_corpus=False,
        )
