"""Evaluate Reckon's optional Helix read model over DHDR's canonical records.

Each DHDR certificate embeds the exact RCDR record that produced it.  This runner
indexes those records without rewriting them, measures candidate retrieval against a
structural relevance rule, and then reopens the canonical records for comparison.

The archive has no explicit pair identifier.  Relevance is therefore not inferred
from filename adjacency: two records are relevant when they record the same action,
policy, and predicate but opposite outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from reckon.helix_index import CandidateHit, HelixProjectionIndex
from reckon.investigate import (
    DecisionProjection,
    GraphEdge,
    GraphNode,
    GraphProjection,
    compare_records,
    project_graph,
    project_record,
)
from reckon.investigation_site import write as write_proof
from reckon.record import digest
from reckon.verify import verify


DEFAULT_CERTS = Path("/opt/datahub-decision-records/docs/certs")
DEFAULT_OUT = Path(".artifacts/dhdr-corpus")


@dataclass(frozen=True)
class CorpusItem:
    certificate_path: Path
    record: dict[str, Any]
    projection: DecisionProjection


def load_corpus(directory: Path) -> list[CorpusItem]:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"no certificate JSON files in {directory}")
    items: list[CorpusItem] = []
    seen: set[str] = set()
    for path in paths:
        certificate = json.loads(path.read_text(encoding="utf-8"))
        record = certificate.get("record")
        if not isinstance(record, dict):
            raise ValueError(f"certificate {path} has no embedded record")
        decision_id = record.get("decision_id")
        if not decision_id:
            raise ValueError(f"record in {path} has no decision_id")
        if decision_id in seen:
            raise ValueError(f"duplicate decision_id {decision_id!r} in {path}")
        seen.add(str(decision_id))
        items.append(
            CorpusItem(
                certificate_path=path,
                record=record,
                projection=project_record(record, source_ref=str(path)),
            )
        )
    return items


def structural_key(record: dict[str, Any]) -> str:
    """Return the recorded fields that define a comparable decision family."""
    policy = record.get("policy", {})
    resolution = policy.get("resolution", {})
    return digest(
        {
            "action_id": record.get("action", {}).get("id"),
            "policy_key": policy.get("key"),
            "policy_value": policy.get("resolved_value"),
            "policy_provenance": resolution.get("provenance"),
            "policy_source": resolution.get("source"),
            "predicate": record.get("predicate"),
            "compared_type": record.get("compared", {}).get("type"),
            "execution_path": record.get("execution", {}).get("path_digest"),
        }
    )


def relevant(query: CorpusItem, candidate: CorpusItem) -> bool:
    return (
        query.record.get("outcome") != candidate.record.get("outcome")
        and structural_key(query.record) == structural_key(candidate.record)
    )


def retrieval_filters(item: CorpusItem) -> dict[str, str]:
    projection = item.projection
    return {
        "action_id": projection.action_id,
        "policy_key": projection.policy_key,
        "predicate_id": projection.predicate_id,
        "compared_type": projection.compared_type,
        "execution_path": projection.execution_path,
    }


def merge_projections(items: Iterable[CorpusItem]) -> GraphProjection:
    """Project each certificate as its own run, then deduplicate shared entities."""
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    for item in items:
        graph = project_graph([item.record], source_ref=str(item.certificate_path))
        for node in graph.nodes:
            nodes.setdefault(node.projection_id, node)
        for edge in graph.edges:
            edges.setdefault(edge.projection_id, edge)
    return GraphProjection(tuple(nodes.values()), tuple(edges.values()))


def local_embedding(text: str, dimension: int = 128) -> list[float]:
    """Private deterministic lexical vector; it is not called a semantic embedding."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    features = tokens + [f"{left}\x1f{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * dimension
    for feature in features:
        raw = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(raw[:4], "big") % dimension
        vector[bucket] += 1.0 if raw[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def reciprocal_rank_fusion(
    *rankings: Sequence[CandidateHit], exclude: str, k: int = 60
) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for hit in ranking:
            if hit.projection_id == exclude:
                continue
            scores[hit.projection_id] = scores.get(hit.projection_id, 0.0) + 1.0 / (
                k + hit.rank
            )
    return sorted(scores, key=lambda projection_id: (-scores[projection_id], projection_id))


def relevant_rank(
    ranking: Sequence[str], query: CorpusItem, by_projection: dict[str, CorpusItem]
) -> int | None:
    for rank, projection_id in enumerate(ranking, start=1):
        candidate = by_projection.get(projection_id)
        if candidate is not None and relevant(query, candidate):
            return rank
    return None


def summarize(ranks: Sequence[int | None], cutoffs: Sequence[int] = (1, 5, 10, 20)) -> dict:
    if not ranks:
        raise ValueError("cannot summarize an empty query set")
    found = [rank for rank in ranks if rank is not None]
    return {
        **{
            f"recall_at_{cutoff}": round(
                sum(rank is not None and rank <= cutoff for rank in ranks) / len(ranks), 4
            )
            for cutoff in cutoffs
        },
        "mrr": round(sum(1.0 / rank for rank in found) / len(ranks), 4),
        "median_rank_found": statistics.median(found) if found else None,
        "not_found": len(ranks) - len(found),
    }


def wait_for_indexes(
    index: HelixProjectionIndex, *, dimension: int, timeout_seconds: float = 30.0
) -> float:
    started = time.perf_counter()
    deadline = started + timeout_seconds
    probe = [1.0] + [0.0] * (dimension - 1)
    while True:
        try:
            index.text_search("readiness probe", limit=1)
            index.vector_search(probe, limit=1)
            return (time.perf_counter() - started) * 1000
        except index.h.HelixError as error:
            if "missing" not in str(error).lower() or time.perf_counter() >= deadline:
                raise
            time.sleep(0.2)


def verification_map(items: Iterable[CorpusItem]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in items:
        report = verify(item.record, requested="C2")
        result[item.projection.projection_id] = {
            "decision_id": item.record["decision_id"],
            "available": report.available,
            "satisfied": report.satisfied,
            "missing": report.missing,
        }
    return result


def evaluate(
    index: HelixProjectionIndex,
    items: list[CorpusItem],
    embeddings: dict[str, list[float]],
    *,
    query_run: str,
    limit: int,
    proof_dir: Path,
) -> dict[str, Any]:
    by_projection = {item.projection.projection_id: item for item in items}
    queries = [item for item in items if item.record.get("run_id") == query_run]
    if not queries:
        raise ValueError(f"no records have run_id {query_run!r}")
    methods = ("bm25", "vector", "hybrid_rrf")
    ranks: dict[str, dict[str, list[int | None]]] = {
        scope: {method: [] for method in methods}
        for scope in ("unconstrained", "structure_constrained")
    }
    comparisons: list[dict[str, Any]] = []
    proof_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:
        text_hits = index.text_search(query.projection.search_text, limit=limit)
        vector_hits = index.vector_search(
            embeddings[query.projection.projection_id], limit=limit
        )
        filters = retrieval_filters(query)
        constrained_text_hits = index.text_search(
            query.projection.search_text,
            limit=limit,
            filters=filters,
            exclude_outcome=query.projection.outcome,
        )
        constrained_vector_hits = index.vector_search(
            embeddings[query.projection.projection_id],
            limit=limit,
            filters=filters,
            exclude_outcome=query.projection.outcome,
        )
        text_ids = [
            hit.projection_id
            for hit in text_hits
            if hit.projection_id != query.projection.projection_id
        ]
        vector_ids = [
            hit.projection_id
            for hit in vector_hits
            if hit.projection_id != query.projection.projection_id
        ]
        hybrid_ids = reciprocal_rank_fusion(
            vector_hits, text_hits, exclude=query.projection.projection_id
        )
        constrained_text_ids = [hit.projection_id for hit in constrained_text_hits]
        constrained_vector_ids = [hit.projection_id for hit in constrained_vector_hits]
        constrained_hybrid_ids = reciprocal_rank_fusion(
            constrained_vector_hits,
            constrained_text_hits,
            exclude=query.projection.projection_id,
        )
        for method, ranking in (
            ("bm25", text_ids),
            ("vector", vector_ids),
            ("hybrid_rrf", hybrid_ids),
        ):
            ranks["unconstrained"][method].append(
                relevant_rank(ranking, query, by_projection)
            )
        for method, ranking in (
            ("bm25", constrained_text_ids),
            ("vector", constrained_vector_ids),
            ("hybrid_rrf", constrained_hybrid_ids),
        ):
            ranks["structure_constrained"][method].append(
                relevant_rank(ranking, query, by_projection)
            )

        partner_id = next(
            (
                projection_id
                for projection_id in constrained_hybrid_ids
                if relevant(query, by_projection[projection_id])
            ),
            None,
        )
        if partner_id is None:
            raise AssertionError(
                f"hybrid retrieval found no structurally relevant record for "
                f"{query.record['decision_id']}"
            )
        partner = by_projection[partner_id]
        comparison = compare_records(
            query.record,
            partner.record,
            guarantee="drop-column decision remains justified by captured lineage evidence",
        )
        if (
            comparison.left_capability.available != "C2"
            or comparison.right_capability.available != "C2"
        ):
            raise AssertionError("DHDR comparison lost its recorded C2 capability")
        proof_path = proof_dir / f"{query.record['decision_id']}.html"
        write_proof(comparison, proof_path)
        comparisons.append(
            {
                "query_decision_id": query.record["decision_id"],
                "candidate_decision_id": partner.record["decision_id"],
                "first_recorded_divergence": comparison.first_evidence_divergence,
                "proof": str(proof_path),
            }
        )

    return {
        "query_run": query_run,
        "queries": len(queries),
        "relevance": (
            "same recorded action, policy, predicate, compared type, and execution path; "
            "opposite outcome"
        ),
        "unconstrained": {
            method: summarize(ranks["unconstrained"][method]) for method in methods
        },
        "structure_constrained": {
            "filters": [
                "action_id",
                "policy_key",
                "predicate_id",
                "compared_type",
                "execution_path",
                "outcome != query outcome",
            ],
            **{
                method: summarize(ranks["structure_constrained"][method])
                for method in methods
            },
        },
        "first_recorded_divergences": dict(
            Counter(item["first_recorded_divergence"] for item in comparisons)
        ),
        "comparisons": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certs", type=Path, default=DEFAULT_CERTS)
    parser.add_argument("--url", default="http://127.0.0.1:6970")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--query-run", default="live-before")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    items = load_corpus(args.certs)
    graph = merge_projections(items)
    args.out.mkdir(parents=True, exist_ok=True)
    canonical_path = args.out / "canonical.jsonl"
    canonical_path.write_text(
        "".join(json.dumps(item.record, sort_keys=True) + "\n" for item in items),
        encoding="utf-8",
    )
    before = verification_map(items)
    if any(not report["satisfied"] for report in before.values()):
        raise AssertionError("the source archive contains a record that does not satisfy C2")

    dimension = 128
    embeddings = {
        item.projection.projection_id: local_embedding(
            item.projection.search_text, dimension=dimension
        )
        for item in items
    }
    index = HelixProjectionIndex(args.url)
    index.create_indexes(embedding_dimension=dimension)
    index_wait_ms = wait_for_indexes(index, dimension=dimension)
    first = index.import_projection(graph, embeddings=embeddings)
    second = index.import_projection(graph, embeddings=embeddings)
    node_ids = {node.projection_id for node in graph.nodes}
    edge_ids = {edge.projection_id for edge in graph.edges}
    if index.ids() != node_ids or index.ids(edge=True) != edge_ids:
        raise AssertionError("Helix differs from the deterministic DHDR graph projection")
    if second.nodes_inserted or second.edges_inserted:
        raise AssertionError(f"second import was not idempotent: {second}")

    evaluation = evaluate(
        index,
        items,
        embeddings,
        query_run=args.query_run,
        limit=args.limit,
        proof_dir=args.out / "proofs",
    )
    after = verification_map(items)
    if before != after:
        raise AssertionError("Helix indexing changed canonical Reckon verification")

    result = {
        "corpus": {
            "certificate_directory": str(args.certs),
            "canonical_copy": str(canonical_path),
            "records": len(items),
            "unique_decisions": len({item.record["decision_id"] for item in items}),
            "runs": dict(Counter(item.record.get("run_id") for item in items)),
            "outcomes": dict(Counter(item.record.get("outcome") for item in items)),
            "capability_classes": dict(
                Counter(report["available"] for report in before.values())
            ),
        },
        "projection": {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "digest": digest(
                {"nodes": sorted(node_ids), "edges": sorted(edge_ids)}
            ),
        },
        "first_import": asdict(first),
        "second_import": asdict(second),
        "index_wait_ms": round(index_wait_ms, 3),
        "evaluation": evaluation,
        "verification_digest_before": digest(before),
        "verification_digest_after": digest(after),
        "boundary": (
            "retrieval proposes structurally relevant candidates; canonical RCDR evidence "
            "establishes the comparison; C3 is not certified"
        ),
    }
    result_path = args.out / "result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {
        **result,
        "evaluation": {
            key: value for key, value in evaluation.items() if key != "comparisons"
        },
    }
    print(json.dumps(summary, indent=2))
    print(f"full result: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
