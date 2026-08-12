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

    @property
    def separable(self) -> bool:
        return bool(self.distinguishing or self.only_in_compliant or self.only_in_violating)

    def render(self) -> str:
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
        }


# Fields that differ between any two executions and say nothing about the guarantee.
# Left out of the comparison because a record that "separates" two runs only by their
# timestamps separates every pair of runs, and would report every guarantee testable.
INCIDENTAL = ("recorded_at", "seq", "prev_hash", "run_id", "timestamp")


def discriminates(
    compliant: dict,
    violating: dict,
    guarantee: str,
    *,
    ignore: tuple[str, ...] = INCIDENTAL,
) -> Discrimination:
    """Compare two captured records that differ only in whether `guarantee` holds."""
    left = _flatten(compliant)
    right = _flatten(violating)

    def incidental(path: str) -> bool:
        return any(part in ignore for part in path.replace("[", ".").split("."))

    keys = sorted(set(left) | set(right))
    result = Discrimination(guarantee=guarantee)
    for key in keys:
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
