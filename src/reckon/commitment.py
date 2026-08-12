"""Commitments (consumer app, Slice 0).

Design law 3: every commitment carries an execution obligation under the agent's
control. Design law 4: the obligation declares what class of evidence will witness
it. Neither is defaulted — a commitment that cannot say how it will be checked is
refused at the write path rather than accepted and quietly discounted later.
"""

from dataclasses import dataclass, field

from .record import digest

# A — cryptographic; B — third-party receipt; C — counterparty attestation;
# D — self-attestation. Classified, never scored (design law 4).
EVIDENCE_CLASSES = ("A", "B", "C", "D")


@dataclass
class Obligation:
    statement: str
    evidence_class: str
    evidence_source: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("obligation.statement must not be empty")
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(
                f"obligation.evidence_class must be one of {EVIDENCE_CLASSES}, "
                f"got {self.evidence_class!r}"
            )
        if not self.evidence_source.strip():
            raise ValueError("obligation.evidence_source must not be empty")

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "evidence_class": self.evidence_class,
            "evidence_source": self.evidence_source,
        }


@dataclass
class Commitment:
    agent: str
    objective: str
    obligation: Obligation | None
    obligation_criteria: str
    outcome_criteria: str
    horizon: str
    sources: list[str] = field(default_factory=list)
    commitment_id: str = ""

    def __post_init__(self) -> None:
        if self.obligation is None:
            raise ValueError(
                "a commitment requires an obligation (design law 3): outcomes alone "
                "are insufficient for credentialing"
            )
        for name in ("agent", "objective", "obligation_criteria", "outcome_criteria",
                     "horizon", "commitment_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")

    def _sealed_payload(self) -> dict:
        return {
            "commitment_id": self.commitment_id,
            "objective": self.objective,
            "obligation": self.obligation.to_dict(),
            "obligation_criteria": self.obligation_criteria,
            "outcome_criteria": self.outcome_criteria,
            "horizon": self.horizon,
            "sources": sorted(self.sources),
        }

    def seal(self) -> str:
        return digest(self._sealed_payload())

    def to_dict(self) -> dict:
        payload = self._sealed_payload()
        payload.update({"kind": "commitment", "agent": self.agent, "seal": self.seal()})
        return payload

    def to_sealed_dict(self) -> dict:
        """The commit half of commit-reveal: the seal and nothing else.

        Deliberately opaque. What it does disclose is the one thing that cannot be
        added afterwards — that a commitment of *some* shape existed at this point in
        the sequence. The ledger stamps the time; the payload arrives later.
        """
        return {"kind": "sealed_commitment", "seal": self.seal()}

    def to_reveal_dict(self) -> dict:
        payload = self._sealed_payload()
        payload.update({"kind": "reveal", "agent": self.agent, "seal": self.seal()})
        return payload
