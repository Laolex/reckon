"""Predicate identity (§4.2).

A predicate is identified by the hash of its canonical structure — operator plus
operand identities — not by its name or source location. The LangGraph probe showed
two gates that were indistinguishable in the record while behaving differently; a
name does not survive a refactor and a line number does not separate look-alikes.
"""

import hashlib

FIELD_SEPARATOR = "\x1f"


def canonical_form(operator: str, left: str, right: str) -> str:
    """The bytes that define a predicate's identity.

    Operands are joined with an ASCII unit separator so that no operand value can
    forge a boundary between fields.
    """
    return FIELD_SEPARATOR.join((operator, left, right))


def predicate_id(operator: str, left: str, right: str) -> str:
    digest = hashlib.sha256(canonical_form(operator, left, right).encode("utf-8"))
    return f"p:{digest.hexdigest()[:16]}"


def expression(operator: str, left: str, right: str) -> str:
    """Human rendering. Informational only — never an identity."""
    return f"{left} {operator} {right}"
