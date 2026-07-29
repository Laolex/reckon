"""Per-commitment views: another pure fold, for the pages that show one at a time.

`credential.project` answers "what is this agent's record" in counts. This answers
"what happened to this particular commitment" — when it was sealed, when it was
opened, what the resolver saw. Same rule applies: derived on read, never stored.
"""

from dataclasses import dataclass, field

from .resolve import cell_for


@dataclass
class CommitmentView:
    commitment_id: str
    objective: str
    obligation: dict
    obligation_criteria: str
    outcome_criteria: str
    horizon: str
    sources: list[str]
    seal: str
    disclosed_at: str
    disclosed_seq: int
    sealed_at: str | None = None
    sealed_seq: int | None = None
    resolution: dict | None = None

    @property
    def was_sealed_before_disclosure(self) -> bool:
        """True when the claim was committed to before anyone could read it."""
        return self.sealed_seq is not None

    @property
    def status(self) -> str:
        return "resolved" if self.resolution else "open"

    @property
    def cell(self) -> str | None:
        if not self.resolution:
            return None
        return cell_for(
            self.resolution["obligation_verdict"], self.resolution["outcome_verdict"]
        )


@dataclass
class UnopenedSeal:
    seal: str
    seq: int
    sealed_at: str


@dataclass
class LedgerView:
    agent: str
    commitments: list[CommitmentView] = field(default_factory=list)
    unopened: list[UnopenedSeal] = field(default_factory=list)
    declines: list[dict] = field(default_factory=list)

    @property
    def open_commitments(self) -> list[CommitmentView]:
        return [c for c in self.commitments if c.status == "open"]


def _view_from(record: dict) -> CommitmentView:
    return CommitmentView(
        commitment_id=record["commitment_id"],
        objective=record["objective"],
        obligation=record["obligation"],
        obligation_criteria=record["obligation_criteria"],
        outcome_criteria=record["outcome_criteria"],
        horizon=record["horizon"],
        sources=record["sources"],
        seal=record["seal"],
        disclosed_at=record.get("recorded_at", ""),
        disclosed_seq=record["seq"],
    )


def ledger_view(records: list[dict]) -> LedgerView:
    view = LedgerView(agent=records[0]["agent"] if records else "")
    # seal -> the sealed_commitment record that wrote it, consumed on reveal so a
    # second reveal of the same seal cannot claim to have been sealed in advance.
    pending: dict[str, list[dict]] = {}
    by_id: dict[str, CommitmentView] = {}

    for record in records:
        kind = record.get("kind")

        if kind == "sealed_commitment":
            pending.setdefault(record["seal"], []).append(record)

        elif kind in ("commitment", "reveal"):
            item = _view_from(record)
            if kind == "reveal":
                queue = pending.get(record["seal"]) or []
                if queue:
                    sealed = queue.pop(0)
                    item.sealed_at = sealed.get("recorded_at")
                    item.sealed_seq = sealed["seq"]
            view.commitments.append(item)
            by_id[item.commitment_id] = item

        elif kind == "decline":
            view.declines.append(record)

        elif kind == "resolution":
            target = by_id.get(record["commitment_id"])
            if target is not None:
                target.resolution = record

    for seal, queue in pending.items():
        for record in queue:
            view.unopened.append(
                UnopenedSeal(seal=seal, seq=record["seq"],
                             sealed_at=record.get("recorded_at", ""))
            )
    view.unopened.sort(key=lambda u: u.seq)
    return view
