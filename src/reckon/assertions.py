"""A closed grammar for what a record may assert.

The capability classes say where evidence ends. They do not stop anyone writing a
sentence that quietly crosses the line — "with the gate off this would have been
profitable" is expressible in English, unfalsifiable in fact, and reads exactly like
a claim the record supports.

So the boundary is made mechanical. An assertion is parsed against a closed set of
forms before any verification runs. A form the grammar cannot express is rejected at
parse time, and that rejection is the point: an assertion nobody can certify never
consumes a verification budget, and never reaches a reader dressed as a finding.

The rejection path is the tested path. A grammar whose refusal never fires is a
grammar that accepts everything.
"""

import enum
import re
from dataclasses import dataclass


class UncertifiableAssertion(ValueError):
    """Raised at parse time when an assertion cannot be expressed in the grammar.

    This is the compile error. It fires before verification, not after, so the cost
    of an uncertifiable claim is a rejected parse rather than a report that has to be
    walked back.
    """


class Form(enum.Enum):
    RECORDED_INPUT = "recorded input"
    RECORDED_OUTCOME = "recorded outcome"
    RECORDED_RESOLUTION = "recorded policy resolution"
    DETERMINISTIC_COUNTERFACTUAL = "counterfactual over recorded state"
    STATE_COUPLED_COUNTERFACTUAL = "counterfactual crossing state coupling"


# The maximum class each form can support (§5.1). C3 is never certifiable, so a form
# that maps to it is expressible and permanently uncertifiable — which is exactly the
# distinction this module exists to make, rather than pretending such claims are
# unsayable.
MAX_CLASS = {
    Form.RECORDED_INPUT: "C2",
    Form.RECORDED_OUTCOME: "C2",
    Form.RECORDED_RESOLUTION: "C2",
    Form.DETERMINISTIC_COUNTERFACTUAL: "C2",
    Form.STATE_COUPLED_COUNTERFACTUAL: "C3",
}

# A counterfactual marker says the sentence is hypothetical. It does not say whether
# the hypothetical is answerable from the record.
COUNTERFACTUAL = re.compile(r"\bwould (have|be)\b|\bhad (it|we|they)\b", re.I)

# Terms naming an outcome that depends on how the world reacted. These are what put a
# counterfactual past the state-coupling boundary: the record can replay a decision,
# it cannot replay a market, a customer, or a production incident.
WORLD_REACTION = re.compile(
    r"\b(profit|profitable|loss|lost|earned|revenue|convert(ed|ion)?|churn(ed)?|"
    r"succeeded|failed|better|worse|higher|lower|happened|responded|behaved|"
    r"clicked|bought|renewed|complained)\b",
    re.I,
)


def _state_coupled(text: str) -> bool:
    """Hypothetical AND about how the world reacted.

    Both signals are searched independently rather than in sequence, because the
    order they appear in is a fact about English, not about certifiability:
    "revenue would have been higher" and "would have earned revenue" make the same
    unsupportable claim. An earlier version required the reaction term to follow the
    marker and silently classified the first as certifiable.
    """
    return bool(COUNTERFACTUAL.search(text) and WORLD_REACTION.search(text))


# Ordered most specific first. State-coupling is tested before the deterministic form,
# or a profit claim matches as an ordinary counterfactual and certifies at C2 — the
# precise substitution the grammar exists to prevent.
PATTERNS: list[tuple[Form, object]] = [
    (Form.STATE_COUPLED_COUNTERFACTUAL, _state_coupled),
    (
        Form.DETERMINISTIC_COUNTERFACTUAL,
        re.compile(r"\b(with|without|under)\b.*\bthe (outcome|decision|verdict) would be\b", re.I),
    ),
    (Form.RECORDED_RESOLUTION, re.compile(r"\bpolicy\b.*\bresolved to\b", re.I)),
    (Form.RECORDED_OUTCOME, re.compile(r"\bthe (outcome|decision|verdict) was\b", re.I)),
    (Form.RECORDED_INPUT, re.compile(r"\bthe (input|request|payload) was\b", re.I)),
]


@dataclass(frozen=True)
class Assertion:
    text: str
    form: Form

    @property
    def max_class(self) -> str:
        return MAX_CLASS[self.form]

    @property
    def certifiable(self) -> bool:
        """C3 is expressible and never certifiable (§3, §6)."""
        return self.max_class != "C3"

    def render(self) -> str:
        if self.certifiable:
            return f"{self.form.value}: certifiable up to {self.max_class}"
        return (
            f"{self.form.value}: NOT certifiable at any class — this claim crosses the "
            f"state-coupling boundary, where evidence ends and hypothesis begins"
        )


def parse(text: str) -> Assertion:
    """Match `text` against the closed grammar, or refuse it.

    Refusal is not a failure of the parser. It is the parser doing the only thing that
    keeps the boundary real.
    """
    for form, matcher in PATTERNS:
        hit = matcher(text) if callable(matcher) else matcher.search(text)
        if hit:
            return Assertion(text=text, form=form)
    raise UncertifiableAssertion(
        f"no assertion form matches: {text!r}\n"
        f"Expressible forms: {[f.value for f in Form]}\n"
        "An assertion outside the grammar cannot be certified, so it is refused here "
        "rather than verified into a claim the record does not support."
    )


def certify(text: str) -> Assertion:
    """Parse, then refuse anything that cannot be certified at any class."""
    assertion = parse(text)
    if not assertion.certifiable:
        raise UncertifiableAssertion(assertion.render())
    return assertion
