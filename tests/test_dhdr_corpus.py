import json

import pytest

from experiments.dhdr_corpus import (
    load_corpus,
    local_embedding,
    merge_projections,
    reciprocal_rank_fusion,
    relevant,
    relevant_rank,
    retrieval_filters,
    structural_key,
    summarize,
)
from reckon.helix_index import CandidateHit


def record(decision_id, run_id, outcome, compared, *, predicate_id="p:lineage"):
    return {
        "rcdr_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "sequence": 0,
        "ts": "2026-08-21T00:00:00Z",
        "outcome": outcome,
        "action": {"id": "drop_column", "params_digest": f"sha256:{decision_id}"},
        "candidates": {
            "completeness": "exhaustive",
            "items": [
                {
                    "action_id": "drop_column",
                    "compared_value": compared,
                    "outcome": outcome,
                    "predicate_id": predicate_id,
                }
            ],
        },
        "reads": [],
        "writes": [],
        "execution": {
            "runtime": "python:3.12",
            "deps_digest": "sha256:deps",
            "path_digest": "sha256:path",
            "seed": None,
            "clock": None,
            "pure": True,
        },
        "capture": {"sdk_version": "0.1.1", "emitter": "dhdr/0.1.0"},
        "predicate": {
            "id": predicate_id,
            "operator": "lte",
            "expression": "downstream_consumers lte max_safe_consumers",
        },
        "compared": {"value": compared, "type": "int"},
        "policy": {
            "key": "max_safe_consumers",
            "resolved_value": 0,
            "resolution": {
                "provenance": "bundled",
                "source": "datahub:lineage",
                "revision": str(100 + compared),
            },
        },
    }


def write_certificate(directory, name, value):
    path = directory / name
    path.write_text(json.dumps({"record": value}), encoding="utf-8")
    return path


def hit(item, rank):
    return CandidateHit(
        projection_id=item.projection.projection_id,
        decision_id=item.record["decision_id"],
        source_ref=str(item.certificate_path),
        search_text=item.projection.search_text,
        rank=rank,
    )


def test_loads_embedded_records_without_rewriting_them(tmp_path):
    original = record("d-before", "live-before", "admit", 0)
    path = write_certificate(tmp_path, "1.json", original)

    items = load_corpus(tmp_path)

    assert len(items) == 1
    assert items[0].record == original
    assert items[0].projection.source_ref == str(path)
    assert items[0].projection.capability_class == "C2"


def test_loader_refuses_duplicate_decision_ids(tmp_path):
    value = record("d-same", "live-before", "admit", 0)
    write_certificate(tmp_path, "1.json", value)
    write_certificate(tmp_path, "2.json", value)

    with pytest.raises(ValueError, match="duplicate decision_id"):
        load_corpus(tmp_path)


def test_relevance_is_structural_and_does_not_use_filename_adjacency(tmp_path):
    write_certificate(
        tmp_path, "far-apart-a.json", record("d-before", "live-before", "admit", 0)
    )
    write_certificate(
        tmp_path, "far-apart-z.json", record("d-after", "live-after", "reject", 1)
    )
    write_certificate(
        tmp_path,
        "between.json",
        record("d-other", "live-after", "reject", 1, predicate_id="p:other"),
    )
    by_id = {item.record["decision_id"]: item for item in load_corpus(tmp_path)}

    assert relevant(by_id["d-before"], by_id["d-after"]) is True
    assert relevant(by_id["d-before"], by_id["d-other"]) is False
    assert structural_key(by_id["d-before"].record) == structural_key(
        by_id["d-after"].record
    )
    assert retrieval_filters(by_id["d-before"]) == {
        "action_id": "drop_column",
        "policy_key": "max_safe_consumers",
        "predicate_id": "p:lineage",
        "compared_type": "int",
        "execution_path": "sha256:path",
    }


def test_projection_merges_shared_evidence_entities_deterministically(tmp_path):
    write_certificate(tmp_path, "1.json", record("d-before", "live-before", "admit", 0))
    write_certificate(tmp_path, "2.json", record("d-after", "live-after", "reject", 1))
    items = load_corpus(tmp_path)

    first = merge_projections(items)
    second = merge_projections(items)

    assert first == second
    assert len([node for node in first.nodes if node.label == "Decision"]) == 2
    assert len({node.projection_id for node in first.nodes}) == len(first.nodes)


def test_ranking_uses_any_structurally_relevant_opposite_outcome(tmp_path):
    write_certificate(tmp_path, "1.json", record("d-before", "live-before", "admit", 0))
    write_certificate(tmp_path, "2.json", record("d-same", "live-before", "admit", 0))
    write_certificate(tmp_path, "3.json", record("d-after", "live-after", "reject", 1))
    items = load_corpus(tmp_path)
    query, same, opposite = items
    by_projection = {item.projection.projection_id: item for item in items}

    fused = reciprocal_rank_fusion(
        [hit(query, 1), hit(same, 2), hit(opposite, 3)],
        [hit(query, 1), hit(opposite, 2), hit(same, 3)],
        exclude=query.projection.projection_id,
    )

    assert relevant_rank(fused, query, by_projection) == 1


def test_local_embedding_and_summary_are_deterministic():
    assert local_embedding("same recorded decision") == local_embedding(
        "same recorded decision"
    )
    magnitude = sum(value * value for value in local_embedding("same recorded decision"))
    assert magnitude == pytest.approx(1.0)
    assert summarize([1, 4, None])["recall_at_5"] == pytest.approx(2 / 3, abs=0.0001)
