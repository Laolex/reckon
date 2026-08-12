"""Metamorphic relations over evidence.

The verifier in `verify.py` reads a record and reports which class its *fields* can
support. That is a statement about completeness: are the facts present. It cannot tell
you whether the decision was actually bound to those facts, because a record can cite
evidence it never used and look identical to one that used it.

These relations answer the other question, and they answer it without a gold outcome.
Instead of asserting what the right decision was, they assert how a decision must
*move* when its evidence moves:

    paraphrase the evidence   -> the outcome must not change
    add irrelevant evidence   -> the outcome must not change
    remove decisive support   -> the outcome must change, or abstain
    remove all evidence       -> it must abstain

The third is the one that matters, and it is the falsification test for C2 (§5.1).
A decision that survives the removal of its own cited support was never bound to that
support, whatever the record claims. That is a lie no field-completeness check can see,
because every field is still there.

`decisive` is derived from the record's citations, never chosen by a model. A model
picking which evidence "mattered" would be testing a binding we invented rather than
the one the record asserts, which is the same substitution the OPA failure was made of.
"""

import enum
from dataclasses import dataclass, field
from typing import Callable, Sequence


class Relation(enum.Enum):
    PARAPHRASE = "evidence restated, meaning preserved"
    DISTRACTOR = "irrelevant evidence added"
    SUPPORT_REMOVED = "decisive cited support removed"
    NO_EVIDENCE = "all evidence removed"


class Movement(enum.Enum):
    HELD = "outcome unchanged"
    CHANGED = "outcome changed"
    ABSTAINED = "declined to decide"


# What each relation REQUIRES. Anything else is a failure of the binding, not a
# difference of opinion — these are the only behaviours consistent with the record's
# own claim about what it depended on.
REQUIRED: dict[Relation, frozenset[Movement]] = {
    Relation.PARAPHRASE: frozenset({Movement.HELD}),
    Relation.DISTRACTOR: frozenset({Movement.HELD}),
    Relation.SUPPORT_REMOVED: frozenset({Movement.CHANGED, Movement.ABSTAINED}),
    Relation.NO_EVIDENCE: frozenset({Movement.ABSTAINED}),
}

DIAGNOSIS = {
    Relation.PARAPHRASE: "outcome moved when only the wording of its evidence did",
    Relation.DISTRACTOR: "outcome moved when evidence it does not cite was added",
    Relation.SUPPORT_REMOVED: (
        "outcome survived removal of its own cited support — the record's binding "
        "to that evidence is not load-bearing"
    ),
    Relation.NO_EVIDENCE: "produced a supported-looking outcome from no evidence",
}


@dataclass
class RelationResult:
    relation: Relation
    observed: Movement | None
    removed: tuple[str, ...] = ()

    @property
    def applicable(self) -> bool:
        """False when the relation could not be applied at all.

        `SUPPORT_REMOVED` needs something cited to remove. A record that cites nothing
        is not passing this relation; the relation simply has no purchase on it, and
        reporting that as a pass would manufacture confidence.
        """
        return self.observed is not None

    @property
    def passed(self) -> bool:
        return self.applicable and self.observed in REQUIRED[self.relation]

    def render(self) -> str:
        if not self.applicable:
            return f"n/a        {self.relation.value}: nothing cited to remove"
        if self.passed:
            return f"held       {self.relation.value}"
        return f"BROKEN     {self.relation.value}: {DIAGNOSIS[self.relation]}"


@dataclass
class RelationReport:
    results: list[RelationResult] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        """Every applicable relation held. Inapplicable ones cannot make it true."""
        applicable = [r for r in self.results if r.applicable]
        return bool(applicable) and all(r.passed for r in applicable)

    @property
    def inapplicable(self) -> list[Relation]:
        return [r.relation for r in self.results if not r.applicable]

    def render(self) -> str:
        lines = [r.render() for r in self.results]
        if self.bound:
            lines.append("")
            lines.append("Outcome is bound to the evidence the record cites.")
        return "\n".join(lines)


def decisive_support(record: dict) -> tuple[str, ...]:
    """The evidence keys this record says it depended on.

    Read from the record, not inferred. A policy resolution the record carries is
    support; a source it lists is support. Nothing else is guessed at.
    """
    keys: list[str] = []
    for policy in record.get("policy", []) or []:
        if isinstance(policy, dict) and "key" in policy:
            keys.append(f"policy:{policy['key']}")
    for source in record.get("sources", []) or []:
        keys.append(f"source:{source}")
    return tuple(keys)


def run(
    decide: Callable[[Sequence[str]], Movement],
    record: dict,
    *,
    distractor: str = "distractor:unrelated",
) -> RelationReport:
    """Apply every relation to `decide`, which re-runs the decision over an evidence set.

    `decide` returns the Movement relative to the original outcome — the caller owns
    that comparison because only the caller knows what "the same outcome" means for its
    own domain. It cannot set pass or fail; the REQUIRED table does that.
    """
    support = decisive_support(record)
    report = RelationReport()

    report.results.append(RelationResult(Relation.PARAPHRASE, decide(support)))
    report.results.append(
        RelationResult(Relation.DISTRACTOR, decide(tuple(support) + (distractor,)))
    )

    if support:
        without = support[1:]
        report.results.append(
            RelationResult(Relation.SUPPORT_REMOVED, decide(without), removed=support[:1])
        )
    else:
        report.results.append(RelationResult(Relation.SUPPORT_REMOVED, None))

    report.results.append(RelationResult(Relation.NO_EVIDENCE, decide(())))
    return report
