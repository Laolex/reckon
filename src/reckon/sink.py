"""Sinks. A sink takes a finished record dict and puts it somewhere durable."""

import json
from pathlib import Path
from typing import Protocol


class Sink(Protocol):
    def write(self, record: dict) -> None: ...


class JsonlSink:
    """One JSON object per line. Append-only; the file is the run."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class MemorySink:
    """For tests and for verifying a run without touching disk."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def write(self, record: dict) -> None:
        self.records.append(record)
