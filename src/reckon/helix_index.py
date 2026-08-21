"""Optional HelixDB adapter for a rebuildable RCDR retrieval projection.

The module deliberately imports ``helixdb`` lazily.  Reckon's verifier and canonical
JSONL format retain zero runtime dependencies and do not consult this index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .investigate import GraphEdge, GraphProjection


@dataclass(frozen=True)
class ImportReceipt:
    nodes_inserted: int
    nodes_skipped: int
    edges_inserted: int
    edges_skipped: int


@dataclass(frozen=True)
class CandidateHit:
    projection_id: str
    decision_id: str
    source_ref: str
    search_text: str
    rank: int
    score: float | None = None
    distance: float | None = None


def _sdk():
    try:
        import helixdb
    except ImportError as error:  # pragma: no cover - exercised without the optional extra
        raise RuntimeError(
            "Helix indexing is optional; install reckon-rcdr[helix-evaluation]"
        ) from error
    return helixdb


def _rows(response: Any, name: str) -> list[dict[str, Any]]:
    value = response[name]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "values"):
            if isinstance(value.get(key), list):
                return value[key]
    raise TypeError(f"unexpected Helix response for {name}: {value!r}")


def _properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    """Keep Helix properties scalar while preserving exact projected values."""
    import json

    return {
        key: (
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
            if isinstance(value, (dict, list, tuple))
            else value
        )
        for key, value in properties.items()
        if value is not None
    }


class HelixProjectionIndex:
    """Idempotently materialize a :class:`GraphProjection` in HelixDB."""

    def __init__(self, url: str = "http://127.0.0.1:6970") -> None:
        self.h = _sdk()
        self.client = self.h.Client(url)

    def create_indexes(self, *, embedding_dimension: int | None = None) -> Any:
        h = self.h
        labels = ("Decision", "PolicyResolution", "Predicate", "StateKey")
        edge_labels = ("RESOLVED_POLICY", "EVALUATED", "READ", "WROTE", "STATE_COUPLES")
        request = h.write_batch()
        returned: list[str] = []
        for index, label in enumerate(labels):
            name = f"node_{index}"
            request = request.var_as(
                name,
                h.g().create_index_if_not_exists(
                    h.IndexSpec.node_unique_equality(label, "projection_id")
                ),
            )
            returned.append(name)
        for index, label in enumerate(edge_labels):
            name = f"edge_{index}"
            request = request.var_as(
                name,
                h.g().create_index_if_not_exists(
                    h.IndexSpec.edge_equality(label, "projection_id")
                ),
            )
            returned.append(name)
        request = request.var_as(
            "decision_text",
            h.g().create_index_if_not_exists(h.IndexSpec.node_text("Decision", "search_text")),
        )
        returned.append("decision_text")
        if embedding_dimension is not None:
            request = request.var_as(
                "decision_vector",
                h.g().create_index_if_not_exists(
                    h.IndexSpec.node_vector(
                        "Decision",
                        "embedding",
                        embedding_dimension,
                        h.VectorDistanceMetric.COSINE,
                    )
                ),
            )
            returned.append("decision_vector")
        return self.client.query(h.QueryRequest.write(request.returning(returned)))

    def _exists(self, projection_id: str, *, edge: bool) -> bool:
        h = self.h
        traversal = (
            h.g().e_where(h.SourcePredicate.eq("projection_id", projection_id))
            if edge
            else h.g().n_where(h.SourcePredicate.eq("projection_id", projection_id))
        )
        request = (
            h.read_batch()
            .var_as("matches", traversal.value_map(["projection_id"]))
            .returning(["matches"])
        )
        return bool(_rows(self.client.query(h.QueryRequest.read(request)), "matches"))

    def import_projection(
        self,
        projection: GraphProjection,
        *,
        embeddings: Mapping[str, Sequence[float]] | None = None,
    ) -> ImportReceipt:
        h = self.h
        inserted_nodes = skipped_nodes = inserted_edges = skipped_edges = 0
        for node in projection.nodes:
            if self._exists(node.projection_id, edge=False):
                skipped_nodes += 1
                continue
            properties = _properties(node.properties)
            properties["projection_id"] = node.projection_id
            if embeddings and node.label == "Decision" and node.projection_id in embeddings:
                properties["embedding"] = list(embeddings[node.projection_id])
            request = (
                h.write_batch()
                .var_as("created", h.g().add_n(node.label, properties))
                .returning(["created"])
            )
            self.client.query(h.QueryRequest.write(request))
            inserted_nodes += 1

        for edge in projection.edges:
            if self._exists(edge.projection_id, edge=True):
                skipped_edges += 1
                continue
            request = (
                h.write_batch()
                .var_as(
                    "source",
                    h.g().n_where(h.SourcePredicate.eq("projection_id", edge.source_id)),
                )
                .var_as(
                    "target",
                    h.g().n_where(h.SourcePredicate.eq("projection_id", edge.target_id)),
                )
                .var_as(
                    "created",
                    h.g()
                    .n(h.NodeRef.var("source"))
                    .add_e(
                        edge.label,
                        h.NodeRef.var("target"),
                        {"projection_id": edge.projection_id, **_properties(edge.properties)},
                    ),
                )
                .returning(["created"])
            )
            self.client.query(h.QueryRequest.write(request))
            inserted_edges += 1
        return ImportReceipt(inserted_nodes, skipped_nodes, inserted_edges, skipped_edges)

    def _hits(self, response: Any, *, vector: bool) -> list[CandidateHit]:
        return [
            CandidateHit(
                projection_id=row["projection_id"],
                decision_id=row["decision_id"],
                source_ref=row["source_ref"],
                search_text=row["search_text"],
                rank=rank,
                score=float(row["score"]) if row.get("score") is not None else None,
                distance=(float(row["distance"]) if vector and row.get("distance") is not None else None),
            )
            for rank, row in enumerate(_rows(response, "hits"), start=1)
        ]

    def text_search(self, query: str, *, limit: int = 20) -> list[CandidateHit]:
        h = self.h
        request = (
            h.read_batch()
            .var_as(
                "hits",
                h.g()
                .n_with_label("Decision")
                .text_search("Decision", "search_text", query, limit)
                .project(
                    [
                        h.PropertyProjection.new("projection_id"),
                        h.PropertyProjection.new("decision_id"),
                        h.PropertyProjection.new("source_ref"),
                        h.PropertyProjection.new("search_text"),
                        h.PropertyProjection.renamed("$score", "score"),
                    ]
                ),
            )
            .returning(["hits"])
        )
        return self._hits(self.client.query(h.QueryRequest.read(request)), vector=False)

    def vector_search(self, embedding: Sequence[float], *, limit: int = 20) -> list[CandidateHit]:
        h = self.h
        request = (
            h.read_batch()
            .var_as(
                "hits",
                h.g()
                .n_with_label("Decision")
                .vector_search("Decision", "embedding", list(embedding), limit)
                .project(
                    [
                        h.PropertyProjection.new("projection_id"),
                        h.PropertyProjection.new("decision_id"),
                        h.PropertyProjection.new("source_ref"),
                        h.PropertyProjection.new("search_text"),
                        h.PropertyProjection.renamed("$distance", "distance"),
                    ]
                ),
            )
            .returning(["hits"])
        )
        return self._hits(self.client.query(h.QueryRequest.read(request)), vector=True)

    def ids(self, *, edge: bool = False) -> set[str]:
        h = self.h
        predicate = h.SourcePredicate.neq("projection_id", "")
        traversal = h.g().e_where(predicate) if edge else h.g().n_where(predicate)
        request = (
            h.read_batch()
            .var_as("items", traversal.value_map(["projection_id"]))
            .returning(["items"])
        )
        return {
            row["projection_id"]
            for row in _rows(self.client.query(h.QueryRequest.read(request)), "items")
            if row.get("projection_id")
        }
