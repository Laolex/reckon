"""Run-level verification and C3 boundary reporting (§5.1, §5.2, §4.7)."""

import pytest

from reckon import MemorySink, Recorder
from reckon.run import boundary, verify_run


def make_run(*, second_provenance="bundled", exhaustive=True):
    sink = MemorySink()
    rec = Recorder(sink=sink, run_id="r-1", emitter="test")

    with rec.decision(action="price", pure=True) as d:
        d.policy("policy.limit", value=100, provenance="bundled", source="opa:bundle")
        d.candidate("price", compared_value=10, outcome="admit", predicate="p:a")
        d.candidates_exhaustive()
        d.check("lt", left="quote", value=10, right="policy.limit")
        d.write("book.mid", 10)
        d.admit()

    with rec.decision(action="transfer", pure=True) as d:
        d.policy("policy.limit", value=100, provenance=second_provenance, source="opa:api")
        if exhaustive:
            d.candidate("transfer", compared_value=50, outcome="admit", predicate="p:b")
            d.candidates_exhaustive()
        d.read("book.mid", 10, source="engine")
        d.check("lt", left="size", value=50, right="policy.limit")
        d.write("position.net", 50)
        d.admit()

    with rec.decision(action="hedge", pure=True) as d:
        d.policy("policy.limit", value=100, provenance="bundled", source="opa:bundle")
        d.candidate("hedge", compared_value=5, outcome="admit", predicate="p:c")
        d.candidates_exhaustive()
        d.read("position.net", 50, source="engine")
        d.check("lt", left="delta", value=5, right="policy.limit")
        d.admit()

    return sink.records


# --- run-level class (§5.1 applied across a run) --------------------------------


def test_a_run_is_only_as_strong_as_its_weakest_decision():
    """One under-instrumented decision caps the run. Averaging would hide it."""
    report = verify_run(make_run(exhaustive=False), requested="C2")
    assert report.available == "C1"
    assert report.satisfied is False


def test_a_fully_instrumented_run_supports_c2():
    report = verify_run(make_run(), requested="C2")
    assert report.available == "C2"
    assert report.satisfied is True
    assert report.shortfalls == []


def test_the_run_report_names_the_decisions_that_fall_short():
    """'Which one' is the useful output — it says what to instrument next."""
    records = make_run(exhaustive=False)
    report = verify_run(records, requested="C2")
    assert len(report.shortfalls) == 1
    decision_id, available, missing = report.shortfalls[0]
    assert decision_id == records[1]["decision_id"]
    assert available == "C1"
    assert "candidates.completeness = exhaustive" in missing


def test_run_report_counts_decisions_by_class():
    report = verify_run(make_run(exhaustive=False), requested="C2")
    assert report.counts == {"C2": 2, "C1": 1}


def test_run_report_carries_no_score():
    rendered = verify_run(make_run(exhaustive=False), requested="C2").render()
    for banned in ("%", "score", "confidence", "probability", "average"):
        assert banned not in rendered.lower()


def test_unknown_provenance_anywhere_caps_the_run_at_c0():
    report = verify_run(make_run(second_provenance="unknown"), requested="C1")
    assert report.available == "C0"
    assert report.satisfied is False


# --- the C3 boundary (§4.7, §5.1) ----------------------------------------------


def test_boundary_marks_state_coupled_successors_as_hypothesis():
    """Changing decision 0 perturbs state that 1 reads, and 1 perturbs what 2 reads."""
    records = make_run()
    edge = boundary(records, records[0]["decision_id"])
    assert edge.evidence == [records[0]["decision_id"]]
    assert edge.hypothesis == [records[1]["decision_id"], records[2]["decision_id"]]


def test_boundary_names_the_edge_at_which_evidence_ends():
    records = make_run()
    edge = boundary(records, records[0]["decision_id"])
    assert edge.edges[0] == (records[0]["decision_id"], "book.mid", records[1]["decision_id"])


def test_a_decision_nothing_reads_from_has_no_hypothesis_region():
    """Not every counterfactual crosses the cliff. The last decision writes nothing."""
    records = make_run()
    edge = boundary(records, records[2]["decision_id"])
    assert edge.hypothesis == []
    assert edge.edges == []


def test_boundary_never_certifies_downstream():
    records = make_run()
    rendered = boundary(records, records[0]["decision_id"]).render()
    assert "hypothesis" in rendered.lower()
    assert "certif" not in rendered.lower().replace("not certifiable", "")


def test_boundary_refuses_an_unknown_decision():
    with pytest.raises(ValueError, match="not in this run"):
        boundary(make_run(), "d-nope")
