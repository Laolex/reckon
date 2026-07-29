"""The credential: a pure fold over the ledger.

Nothing here is stored. Every figure is derived from the whole record — no windows,
no filters, no rates. Counts and classes only, because a ratio invites a reader to
believe a precision the evidence does not carry.
"""

from dataclasses import dataclass

from .commitment import EVIDENCE_CLASSES
from .integrity import IntegrityReport, verify_ledger
from .resolve import CELLS


@dataclass
class Credential:
    agent: str
    genesis: str | None
    commitments: int
    declines: int
    sealed: int
    revealed: int
    unopened: int
    resolved: int
    unresolved: int
    cells: dict[str, int]
    evidence_mix: dict[str, int]
    completeness: str
    integrity: IntegrityReport

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "genesis": self.genesis,
            "commitments": self.commitments,
            "declines": self.declines,
            "sealed": self.sealed,
            "revealed": self.revealed,
            "unopened": self.unopened,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "cells": self.cells,
            "evidence_mix": self.evidence_mix,
            "completeness": self.completeness,
            "integrity": self.integrity.to_dict(),
        }


def project(records: list[dict]) -> Credential:
    integrity = verify_ledger(records)
    cells = {name: 0 for name in CELLS}
    evidence_mix = {name: 0 for name in EVIDENCE_CLASSES}

    agent = records[0]["agent"] if records else ""
    genesis = records[0].get("recorded_at") if records else None
    commitments = declines = sealed = revealed = resolved = 0

    for record in records:
        kind = record.get("kind")
        # A commitment written in the clear and one opened from a seal are the same
        # thing to a reader — both disclose their payload, so both are classifiable.
        if kind in ("commitment", "reveal"):
            commitments += 1
            evidence_mix[record["obligation"]["evidence_class"]] += 1
            if kind == "reveal":
                revealed += 1
        elif kind == "sealed_commitment":
            sealed += 1
        elif kind == "decline":
            declines += 1
        elif kind == "resolution":
            resolved += 1
            cells[record["cell"]] += 1

    if integrity.gaps:
        completeness = "partial"
    elif declines:
        completeness = "full"
    else:
        completeness = "commitments-only"

    return Credential(
        agent=agent,
        genesis=genesis,
        commitments=commitments,
        declines=declines,
        sealed=sealed,
        revealed=revealed,
        unopened=sealed - revealed,
        resolved=resolved,
        unresolved=commitments - resolved,
        cells=cells,
        evidence_mix=evidence_mix,
        completeness=completeness,
        integrity=integrity,
    )
