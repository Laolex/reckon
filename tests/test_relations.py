"""Metamorphic relations: does the outcome actually follow its evidence.

The decision functions here are stand-ins with known behaviour, because the point
under test is the relation table and its verdicts, not anybody's real policy engine.
"""

from reckon.relations import (
    Movement,
    Relation,
    RelationResult,
    decisive_support,
    run,
)

RECORD = {
    "policy": [
        {"key": "max_amount", "resolved_value": 9000},
        {"key": "sanctioned", "resolved_value": ["IR"]},
    ],
    "sources": ["ledger.csv"],
}


def bound(evidence):
    """Genuinely bound: depends on every citation, so removing any one moves it.

    An earlier version of this fixture depended only on `policy:max_amount` while the
    record cited three things. Once SUPPORT_REMOVED began testing each citation, the
    fixture failed — correctly. It was itself an instance of the decorative binding
    this module exists to detect, which is a good sign for the module and a bad one
    for the original test.
    """
    if not evidence:
        return Movement.ABSTAINED
    cited = {"policy:max_amount", "policy:sanctioned", "source:ledger.csv"}
    # Present, not counted: DISTRACTOR adds a fourth item and must not move it.
    return Movement.HELD if cited <= set(evidence) else Movement.CHANGED


def partly_decorative(evidence):
    """Cites three, depends on one. The other two carried no weight."""
    if not evidence:
        return Movement.ABSTAINED
    return Movement.HELD if "policy:max_amount" in evidence else Movement.CHANGED


def decorative(evidence):
    """The failure this module exists to catch: the outcome never moves at all.

    A record produced by this decision function is field-complete and cites its
    evidence. Nothing in `verify.py` can tell it apart from `bound`.
    """
    return Movement.HELD


def test_decisive_support_is_read_not_inferred():
    assert decisive_support(RECORD) == (
        "policy:max_amount",
        "policy:sanctioned",
        "source:ledger.csv",
    )


def test_a_bound_outcome_holds_every_relation():
    report = run(bound, RECORD)
    assert report.bound
    assert "bound to the evidence" in report.render()


def test_a_decorative_binding_fails_on_support_removed():
    report = run(decorative, RECORD)
    assert not report.bound
    broken = [r for r in report.results if not r.passed]
    assert {r.relation for r in broken} == {
        Relation.SUPPORT_REMOVED,
        Relation.NO_EVIDENCE,
    }
    assert "not load-bearing" in report.render()


def test_decorative_citations_are_named_individually():
    """The finding worth having is WHICH citations carried no weight."""
    report = run(partly_decorative, RECORD)
    assert not report.bound
    assert report.decorative == ["policy:sanctioned", "source:ledger.csv"]
    assert "policy:sanctioned" in report.render()


def test_paraphrase_and_distractor_must_not_move_the_outcome():
    def skittish(evidence):
        """Moves when anything at all is added — a distractor must not do that."""
        return Movement.CHANGED if len(evidence) > 3 else Movement.HELD

    report = run(skittish, RECORD)
    failed = {r.relation for r in report.results if not r.passed}
    assert Relation.DISTRACTOR in failed


def test_a_record_citing_nothing_is_never_reported_as_bound():
    """Found by running this against a real dhdr record, which cites via `reads`.

    Every relation over the support set is vacuous without one, and reporting either
    a pass or a failure manufactures a finding about a record the reader could not
    read. The first version accused such records of a broken binding, then — once
    guarded — certified them as bound on the strength of NO_EVIDENCE alone.
    """
    report = run(bound, {"policy": [], "sources": []})
    assert not report.bound
    assert set(report.inapplicable) == {
        Relation.PARAPHRASE,
        Relation.DISTRACTOR,
        Relation.SUPPORT_REMOVED,
    }
    assert "the record cites no evidence" in report.render()
    assert "Outcome is bound" not in report.render()


def test_reads_are_citations_too():
    """A real dhdr record carries a single `policy` dict and cites through `reads`."""
    from reckon.relations import decisive_support

    real_shape = {
        "policy": {"key": "max_safe_consumers", "resolved_value": 0},
        "reads": [{"key": "downstream_consumers", "value_digest": "sha256:abc"}],
    }
    assert decisive_support(real_shape) == (
        "policy:max_safe_consumers",
        "read:downstream_consumers",
    )


def test_bound_requires_at_least_one_applicable_relation():
    report = run(bound, {})
    assert not report.bound or report.results


def test_required_table_covers_every_relation():
    """A relation with no requirement would silently pass anything."""
    from reckon.relations import REQUIRED

    assert set(REQUIRED) == set(Relation)
    assert all(REQUIRED[r] for r in Relation)


def test_result_render_names_the_relation_that_broke():
    result = RelationResult(Relation.SUPPORT_REMOVED, Movement.HELD)
    assert not result.passed
    assert "cited support" in result.render()
