"""Ledger integrity: gaps, forks, broken seals.

Output is shaped like the verifier in `verify.py` — the specific evidence that
failed, never a score.
"""

from dataclasses import dataclass, field

from .commitment import Commitment, Obligation
from .ledger import GENESIS_HASH
from .record import digest


@dataclass
class IntegrityReport:
    intact: bool
    gaps: list[tuple[int, int]] = field(default_factory=list)
    forks: list[int] = field(default_factory=list)
    broken_seals: list[str] = field(default_factory=list)
    unmatched_reveals: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.intact:
            return "Record intact: no gaps, no forks, every seal binds."
        lines = []
        for lo, hi in self.gaps:
            lines.append(f"gap        sequence jumps {lo} -> {hi}")
        for seq in self.forks:
            lines.append(f"fork       record {seq} does not link to its predecessor")
        for cid in self.broken_seals:
            lines.append(f"seal       {cid} does not match its sealed fields")
        for cid in self.unmatched_reveals:
            lines.append(
                f"reveal     {cid} was opened without a matching earlier seal"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "intact": self.intact,
            "gaps": [list(g) for g in self.gaps],
            "forks": self.forks,
            "broken_seals": self.broken_seals,
            "unmatched_reveals": self.unmatched_reveals,
        }


def _reseal(record: dict) -> str:
    return Commitment(
        agent=record["agent"],
        objective=record["objective"],
        obligation=Obligation(**record["obligation"]),
        obligation_criteria=record["obligation_criteria"],
        outcome_criteria=record["outcome_criteria"],
        horizon=record["horizon"],
        sources=record["sources"],
        commitment_id=record["commitment_id"],
    ).seal()


def verify_ledger(records: list[dict]) -> IntegrityReport:
    gaps: list[tuple[int, int]] = []
    forks: list[int] = []
    broken: list[str] = []
    unmatched: list[str] = []

    expected_prev = GENESIS_HASH
    previous_seq: int | None = None
    # Seals written and not yet opened. A reveal consumes one, so opening the same
    # seal twice — or opening one that was never written — has nothing to consume.
    pending: list[str] = []

    for record in records:
        seq = record["seq"]
        kind = record.get("kind")

        if previous_seq is not None and seq != previous_seq + 1:
            gaps.append((previous_seq, seq))
        if record["prev_hash"] != expected_prev:
            forks.append(seq)

        if kind == "sealed_commitment":
            pending.append(record["seal"])
        elif kind in ("commitment", "reveal"):
            if _reseal(record) != record["seal"]:
                broken.append(record["commitment_id"])
            if kind == "reveal":
                if record["seal"] in pending:
                    pending.remove(record["seal"])
                else:
                    unmatched.append(record["commitment_id"])

        previous_seq = seq
        expected_prev = digest(record)

    intact = not (gaps or forks or broken or unmatched)
    return IntegrityReport(
        intact=intact,
        gaps=gaps,
        forks=forks,
        broken_seals=broken,
        unmatched_reveals=unmatched,
    )
