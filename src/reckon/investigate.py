"""Project and compare RCDR decisions without weakening Reckon's evidence boundary.

Retrieval systems may use :class:`DecisionProjection` to find a likely pair.  The
comparison itself always runs over the canonical records.  In particular, a changed
outcome is a conclusion to explain; it is never counted as evidence that explains
itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .discrimination import Discrimination, discriminates
from .record import digest
from .run import Boundary, boundary
from .verify import CLASS_NAMES, Report, verify


def _get(value: dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = value
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class DecisionProjection:
    """The searchable subset of a decision, derived only from canonical RCDR fields."""

    projection_id: str
    record_digest: str
    source_ref: str
    decision_id: str
    run_id: str
    sequence: int
    action_id: str
    outcome: str
    predicate_id: str
    predicate_operator: str
    predicate_expression: str
    policy_key: str
    policy_value: str
    policy_provenance: str
    policy_source: str
    policy_revision: str
    compared_value: str
    compared_type: str
    candidates_completeness: str
    capability_class: str
    read_keys: tuple[str, ...]
    write_keys: tuple[str, ...]
    search_text: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["read_keys"] = list(self.read_keys)
        result["write_keys"] = list(self.write_keys)
        return result


def project_record(record: dict[str, Any], *, source_ref: str) -> DecisionProjection:
    """Build a deterministic retrieval projection without inventing missing facts."""
    if not record.get("decision_id"):
        raise ValueError("record is missing decision_id")
    record_digest = digest(record)
    capability = verify(record, requested="C2").available or "none"
    read_keys = tuple(sorted({str(item["key"]) for item in record.get("reads", [])}))
    write_keys = tuple(sorted({str(item["key"]) for item in record.get("writes", [])}))
    parts = (
        _get(record, "action.id"),
        record.get("outcome"),
        _get(record, "predicate.id"),
        _get(record, "predicate.operator"),
        _get(record, "predicate.expression"),
        _get(record, "policy.key"),
        _get(record, "policy.resolved_value"),
        _get(record, "policy.resolution.provenance"),
        _get(record, "policy.resolution.source"),
        _get(record, "policy.resolution.revision"),
        _get(record, "compared.value"),
        _get(record, "compared.type"),
        *read_keys,
        *write_keys,
    )
    return DecisionProjection(
        projection_id=record_digest,
        record_digest=record_digest,
        source_ref=source_ref,
        decision_id=str(record["decision_id"]),
        run_id=str(record.get("run_id", "")),
        sequence=int(record.get("sequence", 0)),
        action_id=_text(_get(record, "action.id")),
        outcome=_text(record.get("outcome")),
        predicate_id=_text(_get(record, "predicate.id")),
        predicate_operator=_text(_get(record, "predicate.operator")),
        predicate_expression=_text(_get(record, "predicate.expression")),
        policy_key=_text(_get(record, "policy.key")),
        policy_value=_text(_get(record, "policy.resolved_value")),
        policy_provenance=_text(_get(record, "policy.resolution.provenance")),
        policy_source=_text(_get(record, "policy.resolution.source")),
        policy_revision=_text(_get(record, "policy.resolution.revision")),
        compared_value=_text(_get(record, "compared.value")),
        compared_type=_text(_get(record, "compared.type")),
        candidates_completeness=_text(_get(record, "candidates.completeness")),
        capability_class=capability,
        read_keys=read_keys,
        write_keys=write_keys,
        search_text=" ".join(_text(part) for part in parts if part is not None),
    )


@dataclass(frozen=True)
class GraphNode:
    projection_id: str
    label: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    projection_id: str
    label: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphProjection:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def _entity_id(label: str, value: Any) -> str:
    return digest({"label": label, "value": value})


def project_graph(
    records: Iterable[dict[str, Any]], *, source_ref: str
) -> GraphProjection:
    """Project decisions, evidence entities, and state coupling from RCDR fields."""
    ordered = sorted(records, key=lambda record: record.get("sequence", 0))
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    decision_ids: dict[str, str] = {}

    def add_node(label: str, projection_id: str, properties: dict[str, Any]) -> None:
        nodes.setdefault(projection_id, GraphNode(projection_id, label, properties))

    def add_edge(
        label: str, source_id: str, target_id: str, properties: dict[str, Any] | None = None
    ) -> None:
        props = properties or {}
        edge_id = digest(
            {"label": label, "source": source_id, "target": target_id, "properties": props}
        )
        edges.setdefault(edge_id, GraphEdge(edge_id, label, source_id, target_id, props))

    for record in ordered:
        decision = project_record(record, source_ref=source_ref)
        decision_ids[decision.decision_id] = decision.projection_id
        add_node("Decision", decision.projection_id, decision.to_dict())

        for label, path, edge_label in (
            ("PolicyResolution", "policy", "RESOLVED_POLICY"),
            ("Predicate", "predicate", "EVALUATED"),
        ):
            value = _get(record, path)
            if value:
                entity_id = _entity_id(label, value)
                add_node(label, entity_id, {"value": _text(value)})
                add_edge(edge_label, decision.projection_id, entity_id)

        for relation, items in (("READ", record.get("reads", [])), ("WROTE", record.get("writes", []))):
            for item in items:
                key = str(item["key"])
                key_id = _entity_id("StateKey", key)
                add_node("StateKey", key_id, {"key": key})
                add_edge(relation, decision.projection_id, key_id)

    # A run's boundary closure gives canonical writer/read dependencies.  Adding the
    # direct edges for each origin keeps retrieval useful without certifying C3.
    for record in ordered:
        origin = str(record["decision_id"])
        for writer, key, reader in boundary(ordered, origin).edges:
            add_edge(
                "STATE_COUPLES",
                decision_ids[writer],
                decision_ids[reader],
                {"key": key},
            )

    return GraphProjection(tuple(nodes.values()), tuple(edges.values()))


EVIDENCE_PRIORITY = (
    "policy.key",
    "policy.resolved_value",
    "policy.resolution.provenance",
    "policy.resolution.source",
    "policy.resolution.revision",
    "predicate.id",
    "predicate.operator",
    "predicate.expression",
    "compared.value",
    "compared.type",
    "candidates.completeness",
    "candidates.items",
    "execution.path_digest",
    "execution.deps_digest",
    "execution.runtime",
    "reads",
    "writes",
)


@dataclass
class Divergence:
    left: dict[str, Any]
    right: dict[str, Any]
    guarantee: str
    discrimination: Discrimination
    left_capability: Report
    right_capability: Report
    first_evidence_divergence: str | None
    left_boundary: Boundary | None = None
    right_boundary: Boundary | None = None

    @property
    def outcome_changed(self) -> bool:
        return self.left.get("outcome") != self.right.get("outcome")

    @property
    def explained(self) -> bool:
        return self.discrimination.separable

    def to_dict(self) -> dict[str, Any]:
        return {
            "guarantee": self.guarantee,
            "left_decision_id": self.left.get("decision_id"),
            "right_decision_id": self.right.get("decision_id"),
            "left_outcome": self.left.get("outcome"),
            "right_outcome": self.right.get("outcome"),
            "outcome_changed": self.outcome_changed,
            "explained": self.explained,
            "first_evidence_divergence": self.first_evidence_divergence,
            "discrimination": self.discrimination.to_dict(),
            "capability": {
                "left": self.left_capability.available,
                "right": self.right_capability.available,
            },
            "c3_boundary": {
                "left": self.left_boundary.to_dict() if self.left_boundary else None,
                "right": self.right_boundary.to_dict() if self.right_boundary else None,
            },
        }

    def render(self) -> str:
        first = self.first_evidence_divergence or "none recorded"
        return "\n".join(
            (
                f"Guarantee: {self.guarantee}",
                f"Pair:      {self.left.get('decision_id')} / {self.right.get('decision_id')}",
                f"Outcomes:  {self.left.get('outcome')} / {self.right.get('outcome')}",
                f"Evidence:  {'separates the pair' if self.explained else 'does not separate the pair'}",
                f"First:     {first}",
                "Available: "
                f"{self.left_capability.available or 'none'} / "
                f"{self.right_capability.available or 'none'}",
                "C3:        not certified; state-coupled consequences remain hypothesis",
            )
        )


def _priority(path: str) -> tuple[int, str]:
    for index, prefix in enumerate(EVIDENCE_PRIORITY):
        if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "["):
            return index, path
    return len(EVIDENCE_PRIORITY), path


def compare_records(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    guarantee: str,
    left_run: list[dict[str, Any]] | None = None,
    right_run: list[dict[str, Any]] | None = None,
) -> Divergence:
    """Explain a pair from canonical evidence and show where C3 begins."""
    finding = discriminates(left, right, guarantee)
    differing = finding.distinguishing + finding.only_in_compliant + finding.only_in_violating
    first = min(differing, key=_priority) if differing else None
    return Divergence(
        left=left,
        right=right,
        guarantee=guarantee,
        discrimination=finding,
        left_capability=verify(left, requested="C2"),
        right_capability=verify(right, requested="C2"),
        first_evidence_divergence=first,
        left_boundary=(boundary(left_run, str(left["decision_id"])) if left_run else None),
        right_boundary=(boundary(right_run, str(right["decision_id"])) if right_run else None),
    )


def capability_name(value: str | None) -> str:
    return "No replay class" if value is None else f"{CLASS_NAMES[value]} ({value})"
