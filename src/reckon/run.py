"""Run-level verification and the C3 boundary (§4.7, §5.1, §5.2).

Two things happen here that cannot happen one record at a time.

The first is that a run's class is its **weakest** decision, not its average. §5.2
forbids aggregating evidence into a single number, and a mean would do exactly that:
it would let ninety well-instrumented decisions hide the one that cannot support the
counterfactual you actually want to run.

The second is the C3 boundary. A changed decision perturbs state that later decisions
read, and past that first flip nothing is replay any more — it is counterfactual
inference. The boundary report locates the edge where evidence ends. It never
certifies what lies beyond it; it labels it hypothesis and stops.
"""

from dataclasses import dataclass, field

from .verify import CLASS_NAMES, LADDER, verify


def _rank(name: str | None) -> int:
    return -1 if name is None else LADDER.index(name)


@dataclass
class RunReport:
    requested: str
    available: str | None
    satisfied: bool
    counts: dict[str, int] = field(default_factory=dict)
    shortfalls: list[tuple[str, str | None, list[str]]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Requested: {CLASS_NAMES[self.requested]} ({self.requested})",
            f"Available: {self.available or 'none'}",
            "Decisions: "
            + ", ".join(f"{name} x{count}" for name, count in sorted(self.counts.items())),
        ]
        if self.shortfalls:
            lines.append("Short:")
            for decision_id, available, missing in self.shortfalls:
                lines.append(f"  {decision_id}  available {available or 'none'}")
                lines.extend(f"    missing {item}" for item in missing)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "requested": self.requested,
            "available": self.available,
            "satisfied": self.satisfied,
            "counts": self.counts,
            "shortfalls": [
                {"decision_id": decision_id, "available": available, "missing": missing}
                for decision_id, available, missing in self.shortfalls
            ],
        }


def verify_run(records: list[dict], *, requested: str) -> RunReport:
    ordered = sorted(records, key=lambda record: record.get("sequence", 0))
    reports = [(record, verify(record, requested=requested)) for record in ordered]

    counts: dict[str, int] = {}
    for _, report in reports:
        key = report.available or "none"
        counts[key] = counts.get(key, 0) + 1

    available = None
    if reports:
        available = min((report.available for _, report in reports), key=_rank)

    shortfalls = [
        (record["decision_id"], report.available, report.missing)
        for record, report in reports
        if report.missing
    ]

    satisfied = (
        requested != "C3"
        and bool(reports)
        and _rank(available) >= _rank(requested if requested in LADDER else "C2")
    )
    return RunReport(
        requested=requested,
        available=available,
        satisfied=satisfied,
        counts=counts,
        shortfalls=shortfalls,
    )


@dataclass
class Boundary:
    origin: str
    evidence: list[str]
    hypothesis: list[str]
    edges: list[tuple[str, str, str]]

    def render(self) -> str:
        lines = [
            f"Counterfactual at: {self.origin}",
            "Evidence:   " + ", ".join(self.evidence),
        ]
        if self.hypothesis:
            lines.append("Hypothesis: " + ", ".join(self.hypothesis))
            lines.append("Evidence ends at:")
            lines.extend(
                f"  {writer} --{key}--> {reader}" for writer, key, reader in self.edges
            )
            lines.append(
                "Everything in the hypothesis region is inference, not replay. "
                "C3 is not certifiable."
            )
        else:
            lines.append("Hypothesis: none — nothing downstream reads what this decision wrote.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "evidence": self.evidence,
            "hypothesis": self.hypothesis,
            "edges": [
                {"writer": writer, "key": key, "reader": reader}
                for writer, key, reader in self.edges
            ],
        }


def boundary(records: list[dict], decision_id: str) -> Boundary:
    """Locate where evidence ends if `decision_id` had gone the other way.

    A decision is downstream if it reads a key written by the origin, or by anything
    already downstream. The closure is taken forward in sequence order only — a
    decision cannot be perturbed by one that had not happened yet.
    """
    ordered = sorted(records, key=lambda record: record.get("sequence", 0))
    index = {record["decision_id"]: position for position, record in enumerate(ordered)}
    if decision_id not in index:
        raise ValueError(f"decision {decision_id!r} is not in this run")

    origin_position = index[decision_id]
    perturbed = {decision_id}
    edges: list[tuple[str, str, str]] = []
    # writer_of[key] is the most recent perturbed decision to have written it.
    writer_of: dict[str, str] = {
        write["key"]: decision_id for write in ordered[origin_position].get("writes", [])
    }

    for record in ordered[origin_position + 1 :]:
        reader = record["decision_id"]
        touched = False
        for read in record.get("reads", []):
            writer = writer_of.get(read["key"])
            if writer is not None:
                edges.append((writer, read["key"], reader))
                touched = True
        if touched:
            perturbed.add(reader)
            for write in record.get("writes", []):
                writer_of[write["key"]] = reader

    hypothesis = [
        record["decision_id"]
        for record in ordered[origin_position + 1 :]
        if record["decision_id"] in perturbed
    ]
    return Boundary(
        origin=decision_id,
        evidence=[decision_id],
        hypothesis=hypothesis,
        edges=edges,
    )
