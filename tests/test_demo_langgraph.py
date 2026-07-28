"""The LangGraph arc's claims, tested.

The strongest of these is the last one: the re-emitted records reproduce all three
observed outcomes. That is what makes the "after" a reconstruction rather than a story
told over the top of the evidence.
"""

from demo.langgraph_replay import (
    absent_terms,
    after,
    as_rcdr,
    observed,
    persisted_bytes,
)
from reckon import verify_run


def test_one_rationale_across_two_outcomes():
    """The record kept the reasoning that did not decide."""
    facts = observed()
    assert len(facts) == 3
    assert len({fact["rationale"] for fact in facts.values()}) == 1
    assert {fact["action"] for fact in facts.values()} == {"skip", "trade"}


def test_the_deciding_value_is_in_zero_persisted_bytes():
    counts = absent_terms()
    assert set(counts.values()) == {0}
    # Not a vacuous claim over an empty database.
    assert sum(len(blob) for blob in persisted_bytes().values()) > 10_000


def test_before_the_checkpoint_cannot_support_c1():
    facts = observed()
    records = [as_rcdr(tid, fact, i) for i, (tid, fact) in enumerate(facts.items())]
    report = verify_run(records, requested="C1")
    assert report.satisfied is False
    assert report.available is None


def test_after_the_reemitted_run_supports_c2(capsys):
    records = after()
    capsys.readouterr()
    assert verify_run(records, requested="C2").satisfied is True


def test_the_reconstruction_reproduces_every_observed_outcome(capsys):
    """Same three threads, same three answers — now from the record alone."""
    records = after()
    capsys.readouterr()
    reemitted = ["admit" if r["outcome"] == "admit" else "reject" for r in records]
    witnessed = [
        "admit" if fact["action"] == "trade" else "reject" for fact in observed().values()
    ]
    assert reemitted == witnessed
