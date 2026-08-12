"""The append-only ledger.

Two detectors, not one. `prev_hash` proves nothing was edited; `seq` proves nothing
was omitted. An agent that goes quiet through a bad month leaves a hole with a shape,
which is the failure a hash chain alone cannot see.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .commitment import Commitment
from .record import digest
from .sink import Sink

GENESIS_HASH = "sha256:genesis"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Ledger:
    """Appends records for one agent. Never updates, never deletes."""

    def __init__(self, sink: Sink, agent: str, *, start_seq: int = 0,
                 prev_hash: str = GENESIS_HASH) -> None:
        self.sink = sink
        self.agent = agent
        self._next_seq = start_seq
        self._prev_hash = prev_hash

    def append(self, payload: dict) -> dict:
        record = dict(payload)
        record["agent"] = self.agent
        record["seq"] = self._next_seq
        record["prev_hash"] = self._prev_hash
        record.setdefault("recorded_at", _now())
        self.sink.write(record)
        self._next_seq += 1
        self._prev_hash = digest(record)
        return record

    def _own(self, commitment: Commitment) -> None:
        if commitment.agent != self.agent:
            raise ValueError(
                f"commitment belongs to {commitment.agent!r}, ledger is {self.agent!r}"
            )

    def commit(self, commitment: Commitment) -> dict:
        self._own(commitment)
        return self.append(commitment.to_dict())

    def seal_only(self, commitment: Commitment) -> dict:
        """Write the commit half. The payload stays with the agent until reveal."""
        self._own(commitment)
        return self.append(commitment.to_sealed_dict())

    def reveal(self, commitment: Commitment) -> dict:
        """Open a previously sealed commitment. The seal is recomputed, not copied."""
        self._own(commitment)
        return self.append(commitment.to_reveal_dict())

    def decline(self, *, reason: str) -> dict:
        if not reason.strip():
            raise ValueError("decline requires a reason — a blank decline is a gap")
        return self.append({"kind": "decline", "reason": reason})


def read(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
