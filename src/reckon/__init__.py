"""Reckon — the capture layer for autonomous decisions.

Emits RCDR v0.1 records (`docs/RCDR-v0.1.md`) and verifies which replay capability
class a record actually supports. Capture is the primitive; replay exists to prove
capture worked.
"""

from .emit import Decision, Recorder
from .execution import SDK_VERSION
from .sink import JsonlSink, MemorySink, Sink
from .verify import Report, verify

__all__ = [
    "Decision",
    "JsonlSink",
    "MemorySink",
    "Recorder",
    "Report",
    "SDK_VERSION",
    "Sink",
    "verify",
]
