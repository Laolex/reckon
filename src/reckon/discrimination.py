"""Can this record tell a compliant run from a violating one?

Reckon's claim is that no record carries its own soundness proof. Until now that has
been argued, plus one instance found by accident: the OPA probe, where identical input
and bundle revision produced opposite decisions because config sat outside the bundle
roots. The record looked complete. Every field a reviewer would check was present and
correct. It still could not distinguish the two runs.

This is that finding as a procedure rather than an anecdote. Build two executions that
differ only in whether a guarantee holds, capture both, and ask whether the captured
fields separate them. If they do not, the guarantee is not merely unproven — it is
**untestable from this record**, and no amount of additional logging at the same level
of detail will fix it, because the discriminating state was never captured at all.

The output names the fields, because "your record is insufficient" is a complaint and
"these 14 fields are identical across a compliant and a violating run" is a finding.
"""

from dataclasses import dataclass, field
from typing import Any


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten to leaf paths, so a difference nested three levels down is still visible.

    Comparing whole subtrees would report `execution` as differing and leave the reader
    to find out which part, which is the summary the rest of this module exists to avoid.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        out = {}
        for i, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}[{i}]"))
        return out
    return {prefix: value}


@dataclass
class Discrimination:
    guarantee: str
    identical: list[str] = field(default_factory=list)
    distinguishing: list[str] = field(default_factory=list)
    only_in_compliant: list[str] = field(default_factory=list)
    only_in_violating: list[str] = field(default_factory=list)
    conclusion_differs: bool = False

    @property
    def separable(self) -> bool:
        """Whether the EVIDENCE separates the pair. The conclusion does not count.

        Letting the recorded outcome count as separation makes every pair trivially
        testable: a record holding nothing but `{input, outcome}` with identical
        inputs and opposite outcomes would certify, when it is the exact record that
        proves nothing about why. That is the OPA shape, and an earlier version of
        this module reported it separable — the failure this module exists to detect,
        reintroduced inside the module.
        """
        return bool(self.distinguishing or self.only_in_compliant or self.only_in_violating)

    @property
    def unexplained_flip(self) -> bool:
        """The conclusion changed and nothing in the evidence accounts for it.

        The strongest finding this can produce. Not "we cannot tell" but "the record
        documents a change of outcome it cannot explain".
        """
        return self.conclusion_differs and not self.separable

    def render(self) -> str:
        if self.unexplained_flip:
            return "\n".join(
                [
                    f"Guarantee: {self.guarantee}",
                    "Testable:  NO — and the outcome differs anyway",
                    f"           {len(self.identical)} evidence fields, all identical",
                    "           The record documents a change of outcome that nothing",
                    "           in its own evidence accounts for.",
                ]
            )
        if self.separable:
            lines = [
                f"Guarantee: {self.guarantee}",
                "Testable:  yes — the record separates a compliant run from a violating one",
            ]
            for path in self.distinguishing:
                lines.append(f"           differs at {path}")
            for path in self.only_in_compliant:
                lines.append(f"           present only when compliant: {path}")
            for path in self.only_in_violating:
                lines.append(f"           present only when violating: {path}")
            return "\n".join(lines)
        return "\n".join(
            [
                f"Guarantee: {self.guarantee}",
                "Testable:  NO — a compliant and a violating run produce identical records",
                f"           {len(self.identical)} captured fields, none of them discriminating",
                "           The state that decides this guarantee was never captured.",
                "           More logging at this level of detail cannot fix it.",
            ]
        )

    def to_dict(self) -> dict:
        return {
            "guarantee": self.guarantee,
            "separable": self.separable,
            "identical": self.identical,
            "distinguishing": self.distinguishing,
            "only_in_compliant": self.only_in_compliant,
            "only_in_violating": self.only_in_violating,
            "conclusion_differs": self.conclusion_differs,
            "unexplained_flip": self.unexplained_flip,
        }


# Fields that differ between any two executions and say nothing about the guarantee.
# Left out because a record that "separates" two runs only by their timestamps
# separates every pair, and would report every guarantee testable.
INCIDENTAL = ("recorded_at", "seq", "prev_hash", "run_id", "timestamp", "ts", "decision_id")

# The conclusion under examination. Excluded from evidential separation because it is
# the thing being explained, not evidence for it.
CONCLUSION = ("outcome",)


def discriminates(
    compliant: dict,
    violating: dict,
    guarantee: str,
    *,
    ignore: tuple[str, ...] = INCIDENTAL,
    conclusion: tuple[str, ...] = CONCLUSION,
) -> Discrimination:
    """Compare two captured records that differ only in whether `guarantee` holds."""
    left = _flatten(compliant)
    right = _flatten(violating)

    def incidental(path: str) -> bool:
        return any(part in ignore for part in path.replace("[", ".").split("."))

    def is_conclusion(path: str) -> bool:
        """Top-level only. `candidates.items[0].outcome` is a per-candidate verdict —
        evidence about how the decision was reached — not the conclusion itself.
        Matching any path part named `outcome` swallowed those too, which discarded
        real evidence in dhdr records where each candidate carries its own verdict."""
        return path in conclusion

    keys = sorted(set(left) | set(right))
    result = Discrimination(guarantee=guarantee)
    for key in keys:
        if is_conclusion(key):
            if left.get(key) != right.get(key):
                result.conclusion_differs = True
            continue
        if incidental(key):
            continue
        if key in left and key not in right:
            result.only_in_compliant.append(key)
        elif key in right and key not in left:
            result.only_in_violating.append(key)
        elif left[key] == right[key]:
            result.identical.append(key)
        else:
            result.distinguishing.append(key)
    return result
