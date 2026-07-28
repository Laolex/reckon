"""Record structures (§4). These emit the RCDR field names exactly.

Nothing here infers a missing value. Where the emitter cannot establish a fact, the
record says so — `provenance: unknown`, `completeness: taken_only` — because a format
with no way to admit ignorance emits records that silently claim a class they cannot
support (§4.4).
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

PROVENANCE = ("bundled", "runtime_override", "environment", "computed", "unknown")
COMPLETENESS = ("exhaustive", "partial", "taken_only")
OUTCOMES = ("admit", "reject")


def digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass
class Policy:
    key: str
    resolved_value: Any
    provenance: str
    source: str
    revision: str | None = None

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(
                f"policy.resolution.provenance must be one of {PROVENANCE}, "
                f"got {self.provenance!r}. Use 'unknown' when it cannot be established."
            )

    @property
    def resolution_source(self) -> str:
        return f"{self.provenance}:{self.source}"

    def to_dict(self) -> dict:
        resolution: dict[str, Any] = {
            "provenance": self.provenance,
            "source": self.source,
        }
        if self.revision is not None:
            resolution["revision"] = self.revision
        return {
            "key": self.key,
            "resolved_value": self.resolved_value,
            "resolution": resolution,
        }


@dataclass
class Predicate:
    id: str
    operator: str
    expression: str

    def to_dict(self) -> dict:
        return {"id": self.id, "operator": self.operator, "expression": self.expression}


@dataclass
class Candidate:
    action_id: str
    compared_value: Any
    outcome: str
    predicate_id: str

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"candidate outcome must be one of {OUTCOMES}")

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "compared_value": self.compared_value,
            "outcome": self.outcome,
            "predicate_id": self.predicate_id,
        }


@dataclass
class Candidates:
    completeness: str = "taken_only"
    items: list[Candidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.completeness not in COMPLETENESS:
            raise ValueError(f"candidates.completeness must be one of {COMPLETENESS}")

    def to_dict(self) -> dict:
        return {
            "completeness": self.completeness,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class Execution:
    runtime: str
    deps_digest: str
    path_digest: str
    seed: int | None = None
    clock: str | None = None
    pure: bool | None = None

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "deps_digest": self.deps_digest,
            "path_digest": self.path_digest,
            "seed": self.seed,
            "clock": self.clock,
            "pure": self.pure,
        }
