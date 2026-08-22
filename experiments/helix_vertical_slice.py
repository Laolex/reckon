"""Exercise the production-shaped Reckon/Helix boundary against a disposable sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from helixdb import HelixError

from reckon.helix_index import HelixProjectionIndex
from reckon.investigate import compare_records, project_graph
from reckon.investigation_site import write
from reckon.run import verify_run


def record(
    decision_id: str,
    sequence: int,
    value: int,
    outcome: str,
    *,
    reads: tuple[str, ...] = (),
    writes: tuple[str, ...] = (),
) -> dict:
    return {
        "rcdr_version": "0.1",
        "decision_id": decision_id,
        "run_id": "payments-2026-08-21",
        "sequence": sequence,
        "ts": "2026-08-21T12:00:00Z",
        "outcome": outcome,
        "action": {"id": "approve-transfer", "params_digest": f"sha256:params-{value}"},
        "candidates": {
            "completeness": "exhaustive",
            "items": [
                {
                    "action_id": "approve-transfer",
                    "compared_value": value,
                    "outcome": outcome,
                    "predicate_id": "transfer-under-limit",
                }
            ],
        },
        "reads": [
            {"key": key, "value_digest": "sha256:read", "source": "policy-store"}
            for key in reads
        ],
        "writes": [{"key": key, "value_digest": "sha256:write"} for key in writes],
        "execution": {
            "runtime": "python:3.12",
            "deps_digest": "sha256:deps-v9",
            "path_digest": "sha256:approve-transfer-v3",
            "seed": None,
            "clock": None,
            "pure": True,
        },
        "capture": {"sdk_version": "0.1.1", "emitter": "vertical-slice"},
        "predicate": {
            "id": "transfer-under-limit",
            "operator": "lt",
            "expression": "amount < policy.transfer_limit",
        },
        "compared": {"value": value, "type": "int"},
        "policy": {
            "key": "policy.transfer_limit",
            "resolved_value": 5000,
            "resolution": {
                "provenance": "bundled",
                "source": "opa:payments",
                "revision": "bundle-9",
            },
        },
    }


def local_embedding(text: str, dimension: int = 128) -> list[float]:
    vector = [0.0] * dimension
    for token in text.lower().split():
        raw = hashlib.blake2b(token.encode(), digest_size=8).digest()
        vector[int.from_bytes(raw[:4], "big") % dimension] += 1 if raw[4] & 1 else -1
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def wait_for_search(index: HelixProjectionIndex, embedding: list[float]) -> float:
    started = time.perf_counter()
    deadline = started + 30
    while True:
        try:
            index.text_search("readiness probe", limit=1)
            index.vector_search(embedding, limit=1)
            return (time.perf_counter() - started) * 1000
        except HelixError as error:
            if "missing" not in str(error).lower() or time.perf_counter() >= deadline:
                raise
            time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:6970")
    parser.add_argument("--out", type=Path, default=Path(".artifacts/helix-vertical-slice.json"))
    parser.add_argument("--proof", type=Path, default=Path(".artifacts/divergence.html"))
    args = parser.parse_args()

    records = [
        record("payment-low", 0, 4200, "admit", writes=("account.risk",)),
        record("payment-high", 1, 6200, "reject", reads=("account.risk",)),
        record("payment-near", 2, 4900, "admit"),
    ]
    canonical = args.out.parent / "helix-vertical-slice.jsonl"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))

    before = verify_run(records, requested="C2").to_dict()
    graph = project_graph(records, source_ref=str(canonical))
    embeddings = {
        node.projection_id: local_embedding(node.properties["search_text"])
        for node in graph.nodes
        if node.label == "Decision"
    }

    index = HelixProjectionIndex(args.url)
    index.create_indexes(embedding_dimension=128)
    index_wait_ms = wait_for_search(index, [1.0] + [0.0] * 127)
    first = index.import_projection(graph, embeddings=embeddings)
    second = index.import_projection(graph, embeddings=embeddings)

    expected_nodes = {node.projection_id for node in graph.nodes}
    expected_edges = {edge.projection_id for edge in graph.edges}
    if index.ids() != expected_nodes or index.ids(edge=True) != expected_edges:
        raise AssertionError("Helix projection differs from the canonical graph projection")
    if second.nodes_inserted or second.edges_inserted:
        raise AssertionError(f"second import was not idempotent: {second}")

    text_hits = index.text_search("reject transfer amount policy limit", limit=3)
    vector_hits = index.vector_search(
        embeddings[next(node.projection_id for node in graph.nodes if node.label == "Decision")],
        limit=3,
    )
    after = verify_run(records, requested="C2").to_dict()
    if before != after:
        raise AssertionError("retrieval sidecar changed Reckon verification")

    comparison = compare_records(
        records[0],
        records[1],
        guarantee="transfer amount remains below the resolved policy limit",
        left_run=records,
        right_run=records,
    )
    write(comparison, args.proof)
    result = {
        "canonical": str(canonical),
        "proof": str(args.proof),
        "projection": {"nodes": len(graph.nodes), "edges": len(graph.edges)},
        "first_import": first.__dict__,
        "second_import": second.__dict__,
        "index_wait_ms": round(index_wait_ms, 3),
        "text_hits": [hit.__dict__ for hit in text_hits],
        "vector_hits": [hit.__dict__ for hit in vector_hits],
        "comparison": comparison.to_dict(),
        "verification_before": before,
        "verification_after": after,
        "invariant": "Helix is deletable and rebuildable; verification consults canonical RCDR only",
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
