"""The emitter (§7, emitter conformance).

The design rule the whole SDK obeys: **the emitter refuses to guess.** It will raise
rather than invent a policy value it was never told about, or close a decision that
never declared an outcome. A record that quietly fills its own gaps is the failure
mode RCDR exists to prevent.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import execution as execmodel
from . import predicate as pred
from .record import Candidate, Candidates, Execution, Policy, Predicate, digest
from .sink import Sink

OPERATORS = {
    "gte": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in a,
}


class Decision:
    """One decision in flight. Closed by `admit()` or `reject()`."""

    def __init__(self, action: str, params: dict | None, pure: bool | None) -> None:
        self.action = action
        self.params = params or {}
        self.pure = pure
        self.policies: dict[str, Policy] = {}
        self.predicate: Predicate | None = None
        self.governing_key: str | None = None
        self.compared_value: Any = None
        self.compared_type: str | None = None
        self.candidates = Candidates()
        self.outcome: str | None = None
        self.reads: list[dict] = []
        self.writes: list[dict] = []

    # --- policy (§4.4) ---------------------------------------------------------

    def policy(
        self,
        key: str,
        *,
        value: Any,
        provenance: str,
        source: str,
        revision: str | None = None,
    ) -> None:
        """Register the value in force at call time. A pointer will not do."""
        self.policies[key] = Policy(
            key=key,
            resolved_value=value,
            provenance=provenance,
            source=source,
            revision=revision,
        )

    # --- the crossing (§4.2, §4.3) ---------------------------------------------

    def check(self, operator: str, *, left: str, value: Any, right: str) -> bool:
        """Evaluate the predicate and record its structure, operand and policy.

        Returns the real boolean so the caller branches on the same value that was
        recorded. An SDK that records a decision the host did not actually make is
        worse than no record at all.
        """
        if operator not in OPERATORS:
            raise ValueError(f"unknown operator {operator!r}; expected one of {sorted(OPERATORS)}")
        if right not in self.policies:
            raise ValueError(
                f"policy {right!r} is not registered for this decision. "
                "Call .policy() with the value in force before comparing against it."
            )

        policy = self.policies[right]
        self.predicate = Predicate(
            id=pred.predicate_id(operator, left, right),
            operator=operator,
            expression=pred.expression(operator, left, right),
        )
        self.compared_value = value
        self.compared_type = type(value).__name__
        self.governing_key = right
        return bool(OPERATORS[operator](value, policy.resolved_value))

    # --- candidates (§4.6) ------------------------------------------------------

    def candidate(
        self,
        action_id: str,
        *,
        compared_value: Any,
        outcome: str,
        predicate: str,
    ) -> None:
        self.candidates.items.append(
            Candidate(
                action_id=action_id,
                compared_value=compared_value,
                outcome=outcome,
                predicate_id=predicate,
            )
        )

    def candidates_exhaustive(self) -> None:
        """Declare that every candidate considered was recorded.

        Only the caller can know this, which is why it is an explicit statement and
        never inferred from the fact that some candidates were logged.
        """
        self.candidates.completeness = "exhaustive"

    def candidates_partial(self) -> None:
        self.candidates.completeness = "partial"

    # --- state (§4.7) -----------------------------------------------------------

    def read(self, key: str, value: Any, source: str) -> None:
        self.reads.append({"key": key, "value_digest": digest(value), "source": source})

    def write(self, key: str, value: Any) -> None:
        self.writes.append({"key": key, "value_digest": digest(value)})

    # --- outcome (§4.5) ---------------------------------------------------------

    def admit(self) -> None:
        self.outcome = "admit"

    def reject(self) -> None:
        self.outcome = "reject"


class Recorder:
    def __init__(
        self,
        *,
        sink: Sink,
        run_id: str,
        emitter: str,
        seed: int | None = None,
        clock: str | None = None,
    ) -> None:
        self.sink = sink
        self.run_id = run_id
        self.emitter = emitter
        self.seed = seed
        self.clock = clock
        self._sequence = 0

    @contextmanager
    def decision(
        self,
        *,
        action: str,
        params: dict | None = None,
        pure: bool | None = None,
    ) -> Iterator[Decision]:
        decision = Decision(action=action, params=params, pure=pure)
        # If the body raises, the exception propagates untouched: no half-formed
        # record is emitted, and the outcome complaint below never masks it.
        yield decision
        if decision.outcome is None:
            raise ValueError(
                f"decision on action {action!r} closed without an outcome; "
                "call .admit() or .reject()"
            )
        self.sink.write(self._build(decision))

    def _build(self, decision: Decision) -> dict:
        record = {
            "rcdr_version": "0.1",
            "decision_id": f"d-{uuid.uuid4().hex[:12]}",
            "run_id": self.run_id,
            "sequence": self._sequence,
            "ts": datetime.now(timezone.utc).isoformat(),
            "outcome": decision.outcome,
            "action": {
                "id": decision.action,
                "params_digest": digest(decision.params),
            },
            "candidates": decision.candidates.to_dict(),
            "reads": decision.reads,
            "writes": decision.writes,
            "execution": Execution(
                runtime=execmodel.runtime(),
                deps_digest=execmodel.deps_digest(),
                path_digest=execmodel.path_digest(
                    [policy.resolution_source for policy in decision.policies.values()],
                    self.emitter,
                ),
                seed=self.seed,
                clock=self.clock,
                pure=decision.pure,
            ).to_dict(),
            "capture": {
                "sdk_version": execmodel.SDK_VERSION,
                "emitter": self.emitter,
            },
        }
        self._sequence += 1

        if decision.predicate is not None:
            record["predicate"] = decision.predicate.to_dict()
            record["compared"] = {
                "value": decision.compared_value,
                "type": decision.compared_type,
            }
        if decision.governing_key is not None:
            record["policy"] = decision.policies[decision.governing_key].to_dict()
        return record
