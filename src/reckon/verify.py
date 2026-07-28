"""The verifier (§5).

It implements §5.1 exactly and obeys §5.2. The output is type-error shaped: the class
requested, the class actually available, and the specific evidence that separates them.
Never a score — a percentage over incommensurable kinds of missing evidence is the same
false confidence that made the OPA failure undetectable.
"""

from dataclasses import dataclass, field

CLASS_NAMES = {
    "C0": "Identity Replay",
    "C1": "Tightening Replay",
    "C2": "Loosening Replay",
    "C3": "State-Coupled Replay",
}
LADDER = ("C0", "C1", "C2")


@dataclass
class Report:
    requested: str
    available: str | None
    satisfied: bool
    missing: list[str] = field(default_factory=list)

    def render(self) -> str:
        available = self.available or "none"
        lines = [
            f"Requested: {CLASS_NAMES[self.requested]} ({self.requested})",
            f"Available: {available}",
        ]
        if self.missing:
            lines.append(f"Missing:   {self.missing[0]}")
            lines.extend(f"           {item}" for item in self.missing[1:])
        return "\n".join(lines)


def _get(record: dict, path: str):
    node = record
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _unmet_c0(record: dict) -> list[str]:
    missing = [
        f"execution.{name}"
        for name in ("runtime", "deps_digest", "path_digest")
        if not _get(record, f"execution.{name}")
    ]
    seed = _get(record, "execution.seed")
    pure = _get(record, "execution.pure")
    if seed is None and pure is not True:
        # Determinism must be established, not assumed. Either the seed is recorded
        # or the decision function is declared pure.
        missing.append("execution.seed")
        if pure is None:
            missing.append("execution.pure")
    return missing


def _unmet_c1(record: dict) -> list[str]:
    missing = []
    if not _get(record, "predicate.id"):
        missing.append("predicate.id")
    if _get(record, "compared.value") is None:
        missing.append("compared.value")
    if _get(record, "policy.resolved_value") is None:
        missing.append("policy.resolved_value")
    if _get(record, "policy.resolution.provenance") == "unknown":
        # §4.4: the record can say it does not know, and saying so caps it at C0.
        missing.append("policy.resolution.provenance != unknown")
    elif _get(record, "policy.resolution.provenance") is None:
        missing.append("policy.resolution.provenance")
    return missing


def _unmet_c2(record: dict) -> list[str]:
    missing = []
    # §4.6: absent completeness reads as taken_only, the conservative interpretation.
    completeness = _get(record, "candidates.completeness") or "taken_only"
    if completeness != "exhaustive":
        missing.append("candidates.completeness = exhaustive")
    items = _get(record, "candidates.items") or []
    if not items or any(item.get("compared_value") is None for item in items):
        missing.append("candidates.items[].compared_value")
    return missing


UNMET = {"C0": _unmet_c0, "C1": _unmet_c1, "C2": _unmet_c2}


def verify(record: dict, *, requested: str) -> Report:
    if requested not in CLASS_NAMES:
        raise ValueError(f"unknown class {requested!r}; expected one of {sorted(CLASS_NAMES)}")

    unmet_by_class = {name: UNMET[name](record) for name in LADDER}

    available: str | None = None
    for name in LADDER:
        if unmet_by_class[name]:
            break
        available = name

    ceiling = LADDER.index(requested) if requested in LADDER else len(LADDER) - 1
    start = 0 if available is None else LADDER.index(available) + 1
    missing = [item for name in LADDER[start : ceiling + 1] for item in unmet_by_class[name]]

    if requested == "C3":
        # §3, §6: C3 is never certified. The verifier reports where evidence ends and
        # marks everything downstream as hypothesis. No implementation may do otherwise.
        missing.append(
            "C3 (State-Coupled Replay) is not certifiable by any verifier; "
            "past the first flip this is counterfactual inference, not replay"
        )
        return Report(requested=requested, available=available, satisfied=False, missing=missing)

    satisfied = available is not None and LADDER.index(available) >= LADDER.index(requested)
    return Report(requested=requested, available=available, satisfied=satisfied, missing=missing)
