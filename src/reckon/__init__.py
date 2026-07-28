"""Reckon — the capture layer for autonomous decisions.

Emits RCDR v0.1 records (`docs/RCDR-v0.1.md`) and verifies which replay capability
class a record actually supports. Capture is the primitive; replay exists to prove
capture worked.
"""

from .emit import Decision, Recorder
from .execution import SDK_VERSION
from .run import Boundary, RunReport, boundary, verify_run
from .sink import JsonlSink, MemorySink, Sink
from .verify import Report, verify

__all__ = [
    "Boundary",
    "Decision",
    "JsonlSink",
    "MemorySink",
    "Recorder",
    "Report",
    "RunReport",
    "SDK_VERSION",
    "Sink",
    "boundary",
    "verify",
    "verify_run",
]
