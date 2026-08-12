"""Resolution: two independent verdicts, one attribution cell.

Every commitment resolves twice — was the obligation fulfilled, and was the outcome
achieved. The pair is the attribution, and it is a classification. A numeric
"attribution confidence" would manufacture certainty from a handful of events.
"""

from dataclasses import dataclass

VERDICTS = ("met", "missed", "ambiguous", "unresolvable")
CELLS = (
    "attributable",
    "competent_unsuccessful",
    "luck",
    "failure",
    "indeterminate",
)

_GRID = {
    ("met", "met"): "attributable",
    ("met", "missed"): "competent_unsuccessful",
    ("missed", "met"): "luck",
    ("missed", "missed"): "failure",
}


def cell_for(obligation_verdict: str, outcome_verdict: str) -> str:
    for name, value in (("obligation", obligation_verdict), ("outcome", outcome_verdict)):
        if value not in VERDICTS:
            raise ValueError(
                f"{name} verdict must be one of {VERDICTS}, got {value!r}"
            )
    return _GRID.get((obligation_verdict, outcome_verdict), "indeterminate")


@dataclass
class Resolution:
    commitment_id: str
    obligation_verdict: str
    outcome_verdict: str
    evidence_seen: dict

    def __post_init__(self) -> None:
        cell_for(self.obligation_verdict, self.outcome_verdict)
        if not self.evidence_seen:
            raise ValueError(
                "evidence_seen must record what the resolver actually looked at; "
                "a verdict with no evidence is an opinion"
            )

    def cell(self) -> str:
        return cell_for(self.obligation_verdict, self.outcome_verdict)

    def to_dict(self) -> dict:
        return {
            "kind": "resolution",
            "commitment_id": self.commitment_id,
            "obligation_verdict": self.obligation_verdict,
            "outcome_verdict": self.outcome_verdict,
            "cell": self.cell(),
            "evidence_seen": self.evidence_seen,
        }
