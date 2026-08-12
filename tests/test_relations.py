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
    """Honest: holds while its first cited support is present, abstains without any."""
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


def test_paraphrase_and_distractor_must_not_move_the_outcome():
    def skittish(evidence):
        return Movement.CHANGED if len(evidence) != 3 else Movement.HELD

    report = run(skittish, RECORD)
    failed = {r.relation for r in report.results if not r.passed}
    assert Relation.DISTRACTOR in failed


def test_a_record_citing_nothing_cannot_pass_support_removed():
    """Inapplicable is not a pass. Reporting it as one manufactures confidence."""
    report = run(bound, {"policy": [], "sources": []})
    removed = next(r for r in report.results if r.relation is Relation.SUPPORT_REMOVED)
    assert not removed.applicable
    assert not removed.passed
    assert Relation.SUPPORT_REMOVED in report.inapplicable
    assert "nothing cited to remove" in report.render()


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
