"""Measure HelixDB retrieval against Reckon's recorded structural relations.

This is a sidecar experiment. Reckon's JSONL records remain canonical; HelixDB is
only a disposable index over a labelled corpus derived from those records.

Search proposes candidates. The graph may validate a recorded relation, but this
program never infers contradiction from embedding distance or BM25 score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from helixdb import (
    Client,
    HelixError,
    NodeRef,
    Predicate,
    PropertyProjection,
    QueryRequest,
    SourcePredicate,
    VectorDistanceMetric,
    g,
    read_batch,
    write_batch,
)


DEFAULT_PAIRS = Path("/opt/reckon-planning/cosine-probe/pairs.jsonl")
DEFAULT_CACHE = Path(".artifacts/helix-embeddings.json")
DEFAULT_RESULTS = Path(".artifacts/helix-results.json")
CONTRADICTION = re.compile(
    r"^policy (?P<policy>P\d+): "
    r"(?P<a_payout>[0-9a-f]+) (?P<a_outcome>approved|rejected) vs "
    r"(?P<b_payout>[0-9a-f]+) (?P<b_outcome>approved|rejected)$"
)
PARAPHRASE = re.compile(r"^same payout (?P<payout>[0-9a-f]+),")


@dataclass(frozen=True)
class Relation:
    pair_id: str
    relation: str
    why: str
    a: str
    b: str
    policy: str
    a_payout: str
    b_payout: str
    a_outcome: str
    b_outcome: str

    @property
    def a_id(self) -> str:
        return f"{self.pair_id}-a"

    @property
    def b_id(self) -> str:
        return f"{self.pair_id}-b"


@dataclass(frozen=True)
class SearchHit:
    external_id: str
    text: str
    rank: int
    score: float | None = None
    distance: float | None = None


def load_relations(path: Path) -> list[Relation]:
    relations: list[Relation] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        pair_id = f"pair-{index:03d}"
        why = row["why"]
        if row["relation"] == "contradiction":
            match = CONTRADICTION.fullmatch(why)
            if match is None:
                raise ValueError(f"unparseable contradiction relation: {why}")
            data = match.groupdict()
            relations.append(
                Relation(
                    pair_id=pair_id,
                    relation=row["relation"],
                    why=why,
                    a=row["a"],
                    b=row["b"],
                    policy=data["policy"],
                    a_payout=data["a_payout"],
                    b_payout=data["b_payout"],
                    a_outcome=data["a_outcome"],
                    b_outcome=data["b_outcome"],
                )
            )
            continue

        if row["relation"] != "paraphrase":
            raise ValueError(f"unknown relation: {row['relation']}")
        match = PARAPHRASE.match(why)
        if match is None:
            raise ValueError(f"unparseable paraphrase relation: {why}")
        payout = match.group("payout")
        relations.append(
            Relation(
                pair_id=pair_id,
                relation=row["relation"],
                why=why,
                a=row["a"],
                b=row["b"],
                policy="",
                a_payout=payout,
                b_payout=payout,
                a_outcome="",
                b_outcome="",
            )
        )
    if not relations:
        raise ValueError(f"no relations in {path}")
    return relations


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_embedding_cache(path: Path, model: str) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("model") != model or raw.get("dimensions") != 1024:
        return {}
    return raw.get("vectors", {})


def local_hash_embedding(text: str) -> list[float]:
    """Return a private, deterministic lexical vector for plumbing evaluation.

    This is deliberately not described as a semantic embedding. It lets the ANN
    path run without sending the recorded corpus to another service.
    """

    tokens = re.findall(r"[a-z0-9]+", text.lower())
    features = tokens + [f"{left}\x1f{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * 1024
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % len(vector)
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def embed_texts(
    texts: Iterable[str],
    cache_path: Path,
    *,
    provider: str,
    allow_third_party_corpus: bool,
) -> tuple[dict[str, list[float]], str]:
    unique = list(dict.fromkeys(texts))
    model = "reckon-hash-v1" if provider == "local-hash" else "text-embedding-v3"
    cache = load_embedding_cache(cache_path, model)
    missing = [text for text in unique if text_key(text) not in cache]
    if missing:
        if provider == "local-hash":
            for text in missing:
                cache[text_key(text)] = local_hash_embedding(text)
        else:
            if not allow_third_party_corpus:
                raise ValueError(
                    "DashScope would receive the corpus. Re-run with "
                    "--allow-third-party-corpus only after explicit authorization."
                )
            from dotenv import load_dotenv
            from openai import OpenAI

            load_dotenv("/opt/qwen-agent-society/.env")
            client = OpenAI(
                api_key=os.environ["DASHSCOPE_API_KEY"],
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
            for start in range(0, len(missing), 10):
                batch = missing[start : start + 10]
                response = client.embeddings.create(model=model, input=batch)
                ordered = sorted(response.data, key=lambda item: item.index)
                for text, item in zip(batch, ordered, strict=True):
                    if len(item.embedding) != 1024:
                        raise ValueError(
                            f"unexpected embedding dimension: {len(item.embedding)}"
                        )
                    cache[text_key(text)] = item.embedding
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {"model": model, "dimensions": 1024, "vectors": cache},
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    return {text: cache[text_key(text)] for text in unique}, model


def rows(response: Any, name: str) -> list[dict[str, Any]]:
    value = response[name]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "values"):
            if isinstance(value.get(key), list):
                return value[key]
    raise TypeError(f"unexpected Helix response for {name}: {value!r}")


def create_indexes(client: Client) -> Any:
    request = (
        write_batch()
        .var_as("claim_text", g().create_text_index_nodes("Claim", "text"))
        .var_as(
            "claim_vector",
            g().create_vector_index_nodes(
                "Claim", "embedding", 1024, VectorDistanceMetric.COSINE
            ),
        )
        .returning(["claim_text", "claim_vector"])
    )
    return client.query(QueryRequest.write(request))


def wait_for_indexes(client: Client, timeout_seconds: float = 30.0) -> float:
    """Wait until both asynchronously-created indexes accept queries."""

    started = time.perf_counter()
    deadline = started + timeout_seconds
    while True:
        try:
            vector_search(client, [1.0] + [0.0] * 1023, 1)
            text_search(client, "readiness probe", 1)
            return (time.perf_counter() - started) * 1000
        except HelixError as error:
            if "missing" not in str(error).lower() or time.perf_counter() >= deadline:
                raise
            time.sleep(0.2)


def ingest(client: Client, relations: Sequence[Relation], vectors: dict[str, list[float]]) -> None:
    for start in range(0, len(relations), 12):
        request = write_batch()
        returned: list[str] = []
        for relation in relations[start : start + 12]:
            suffix = relation.pair_id.replace("-", "_")
            a_var = f"a_{suffix}"
            b_var = f"b_{suffix}"
            pair_var = f"p_{suffix}"
            a_edge = f"ae_{suffix}"
            b_edge = f"be_{suffix}"
            request = (
                request.var_as(
                    a_var,
                    g().add_n(
                        "Claim",
                        {
                            "external_id": relation.a_id,
                            "pair_id": relation.pair_id,
                            "side": "a",
                            "text": relation.a,
                            "embedding": vectors[relation.a],
                        },
                    ),
                )
                .var_as(
                    b_var,
                    g().add_n(
                        "Claim",
                        {
                            "external_id": relation.b_id,
                            "pair_id": relation.pair_id,
                            "side": "b",
                            "text": relation.b,
                            "embedding": vectors[relation.b],
                        },
                    ),
                )
                .var_as(
                    pair_var,
                    g().add_n(
                        "RecordedRelation",
                        {
                            "external_id": relation.pair_id,
                            "relation": relation.relation,
                            "why": relation.why,
                            "policy": relation.policy,
                            "a_payout": relation.a_payout,
                            "b_payout": relation.b_payout,
                            "a_outcome": relation.a_outcome,
                            "b_outcome": relation.b_outcome,
                        },
                    ),
                )
                .var_as(
                    a_edge,
                    g()
                    .n(NodeRef.var(a_var))
                    .add_e("IN_RECORDED_RELATION", NodeRef.var(pair_var), {"side": "a"}),
                )
                .var_as(
                    b_edge,
                    g()
                    .n(NodeRef.var(b_var))
                    .add_e("IN_RECORDED_RELATION", NodeRef.var(pair_var), {"side": "b"}),
                )
            )
            returned.append(pair_var)
        client.query(QueryRequest.write(request.returning(returned)))


def _hits(response: Any, *, vector: bool) -> list[SearchHit]:
    output: list[SearchHit] = []
    for rank, row in enumerate(rows(response, "hits"), start=1):
        output.append(
            SearchHit(
                external_id=row["external_id"],
                text=row["text"],
                rank=rank,
                score=float(row["score"]) if row.get("score") is not None else None,
                distance=(
                    float(row["distance"])
                    if vector and row.get("distance") is not None
                    else None
                ),
            )
        )
    return output


def vector_search(client: Client, vector: list[float], limit: int) -> list[SearchHit]:
    request = (
        read_batch()
        .var_as(
            "hits",
            g()
            .n_with_label("Claim")
            .where(Predicate.eq("side", "b"))
            .vector_search("Claim", "embedding", vector, limit)
            .project(
                [
                    PropertyProjection.new("external_id"),
                    PropertyProjection.new("text"),
                    PropertyProjection.renamed("$distance", "distance"),
                ]
            ),
        )
        .returning(["hits"])
    )
    return _hits(client.query(QueryRequest.read(request)), vector=True)


def text_search(client: Client, text: str, limit: int) -> list[SearchHit]:
    request = (
        read_batch()
        .var_as(
            "hits",
            g()
            .n_with_label("Claim")
            .where(Predicate.eq("side", "b"))
            .text_search("Claim", "text", text, limit)
            .project(
                [
                    PropertyProjection.new("external_id"),
                    PropertyProjection.new("text"),
                    PropertyProjection.renamed("$score", "score"),
                ]
            ),
        )
        .returning(["hits"])
    )
    return _hits(client.query(QueryRequest.read(request)), vector=False)


def recorded_partner(client: Client, external_id: str) -> dict[str, Any]:
    request = (
        read_batch()
        .var_as("source", g().n_where(SourcePredicate.eq("external_id", external_id)))
        .var_as(
            "relation",
            g()
            .n(NodeRef.var("source"))
            .out("IN_RECORDED_RELATION")
            .value_map(
                [
                    "external_id",
                    "relation",
                    "why",
                    "policy",
                    "a_payout",
                    "b_payout",
                    "a_outcome",
                    "b_outcome",
                ]
            ),
        )
        .var_as(
            "partner",
            g()
            .n(NodeRef.var("source"))
            .out("IN_RECORDED_RELATION")
            .in_("IN_RECORDED_RELATION")
            .where(Predicate.neq("external_id", external_id))
            .value_map(["external_id", "text"]),
        )
        .returning(["relation", "partner"])
    )
    response = client.query(QueryRequest.read(request))
    relation_rows = rows(response, "relation")
    partner_rows = rows(response, "partner")
    if len(relation_rows) != 1 or len(partner_rows) != 1:
        raise ValueError(f"expected one recorded relation and partner for {external_id}: {response}")
    return {"relation": relation_rows[0], "partner": partner_rows[0]}


def reciprocal_rank_fusion(*rankings: Sequence[SearchHit], k: int = 60) -> list[SearchHit]:
    scores: dict[str, float] = {}
    hits: dict[str, SearchHit] = {}
    for ranking in rankings:
        for hit in ranking:
            scores[hit.external_id] = scores.get(hit.external_id, 0.0) + 1.0 / (k + hit.rank)
            hits[hit.external_id] = hit
    ordered = sorted(scores, key=lambda external_id: (-scores[external_id], external_id))
    return [
        SearchHit(
            external_id=external_id,
            text=hits[external_id].text,
            rank=rank,
            score=scores[external_id],
        )
        for rank, external_id in enumerate(ordered, start=1)
    ]


def rank_of_target(hits: Sequence[SearchHit], target_text: str) -> int | None:
    for hit in hits:
        if hit.text == target_text:
            return hit.rank
    return None


def summarize(ranks: Sequence[int | None], cutoffs: Sequence[int]) -> dict[str, Any]:
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


def evaluate(
    client: Client,
    relations: Sequence[Relation],
    vectors: dict[str, list[float]],
    limit: int,
) -> dict[str, Any]:
    vector_ranks: list[int | None] = []
    text_ranks: list[int | None] = []
    hybrid_ranks: list[int | None] = []
    latencies: dict[str, list[float]] = {"vector": [], "bm25": [], "graph": []}
    examples: list[dict[str, Any]] = []

    for relation in relations:
        started = time.perf_counter()
        vector_hits = vector_search(client, vectors[relation.a], limit)
        latencies["vector"].append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        text_hits = text_search(client, relation.a, limit)
        latencies["bm25"].append((time.perf_counter() - started) * 1000)

        hybrid_hits = reciprocal_rank_fusion(vector_hits, text_hits)
        vector_rank = rank_of_target(vector_hits, relation.b)
        text_rank = rank_of_target(text_hits, relation.b)
        hybrid_rank = rank_of_target(hybrid_hits, relation.b)
        vector_ranks.append(vector_rank)
        text_ranks.append(text_rank)
        hybrid_ranks.append(hybrid_rank)

        started = time.perf_counter()
        graph = recorded_partner(client, relation.a_id)
        latencies["graph"].append((time.perf_counter() - started) * 1000)
        if graph["relation"]["relation"] != relation.relation:
            raise AssertionError(f"graph relation drifted for {relation.pair_id}")
        if graph["partner"]["text"] != relation.b:
            raise AssertionError(f"graph partner drifted for {relation.pair_id}")

        if len(examples) < 8 and (
            relation.relation == "contradiction"
            and (hybrid_rank is None or vector_rank == 1 or text_rank == 1)
        ):
            examples.append(
                {
                    "pair_id": relation.pair_id,
                    "query": relation.a,
                    "recorded_partner": relation.b,
                    "relation": asdict(relation),
                    "vector_rank": vector_rank,
                    "bm25_rank": text_rank,
                    "hybrid_rank": hybrid_rank,
                    "vector_top": [asdict(hit) for hit in vector_hits[:3]],
                    "bm25_top": [asdict(hit) for hit in text_hits[:3]],
                }
            )

    def latency_summary(values: Sequence[float]) -> dict[str, float]:
        ordered = sorted(values)
        p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return {
            "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[p95_index], 3),
            "max_ms": round(max(ordered), 3),
        }

    return {
        "corpus": {
            "pairs": len(relations),
            "paraphrase": sum(row.relation == "paraphrase" for row in relations),
            "contradiction": sum(row.relation == "contradiction" for row in relations),
            "unique_texts": len({text for row in relations for text in (row.a, row.b)}),
            "search_limit": limit,
        },
        "vector": summarize(vector_ranks, (1, 5, 10, limit)),
        "bm25": summarize(text_ranks, (1, 5, 10, limit)),
        "hybrid_rrf": summarize(hybrid_ranks, (1, 5, 10, limit * 2)),
        "graph_validation": {
            "validated": len(relations),
            "relation_mismatches": 0,
            "partner_mismatches": 0,
            "claim": "recorded structure validates relations; search scores do not",
        },
        "latency": {name: latency_summary(values) for name, values in latencies.items()},
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--url", default="http://127.0.0.1:6970")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--embedding-provider", choices=("local-hash", "dashscope"), default="local-hash"
    )
    parser.add_argument("--allow-third-party-corpus", action="store_true")
    args = parser.parse_args()

    relations = load_relations(args.pairs)
    vectors, embedding_model = embed_texts(
        (text for relation in relations for text in (relation.a, relation.b)),
        args.cache,
        provider=args.embedding_provider,
        allow_third_party_corpus=args.allow_third_party_corpus,
    )
    client = Client(args.url)

    index_receipts = create_indexes(client)
    index_wait_ms = wait_for_indexes(client)
    started = time.perf_counter()
    ingest(client, relations, vectors)
    ingestion_ms = (time.perf_counter() - started) * 1000
    result = evaluate(client, relations, vectors, args.limit)
    result["environment"] = {
        "helix_url": args.url,
        "helix_image": "ghcr.io/helixdb/helixdb:v0.0.4",
        "storage": "in-memory disposable sidecar",
        "embedding_model": embedding_model,
        "embedding_dimensions": 1024,
        "index_receipts": index_receipts,
        "index_wait_ms": round(index_wait_ms, 3),
        "ingestion_ms": round(ingestion_ms, 3),
    }
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "examples"}, indent=2))
    print(f"full results: {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
