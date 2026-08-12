from reckon.commitment import Commitment, Obligation
from reckon.credential import project
from reckon.ledger import Ledger
from reckon.resolve import Resolution
from reckon.sink import MemorySink


def a_commitment(cid, cls="B"):
    return Commitment(
        agent="helios-3",
        objective="o",
        obligation=Obligation(statement="s", evidence_class=cls, evidence_source="src"),
        obligation_criteria="oc",
        outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z",
        sources=["s"],
        commitment_id=cid,
    )


def build():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.commit(a_commitment("c-0", "A"))
    ledger.commit(a_commitment("c-1", "D"))
    ledger.decline(reason="nothing qualified")
    ledger.append(
        Resolution("c-0", "met", "met", {"tx": "0xabc"}).to_dict()
    )
    ledger.append(
        Resolution("c-1", "missed", "met", {"note": "market moved"}).to_dict()
    )
    return sink.records


def test_counts_are_integers_not_rates():
    c = project(build())
    assert c.commitments == 2
    assert c.declines == 1
    assert c.resolved == 2
    assert c.unresolved == 0
    for value in list(c.cells.values()) + list(c.evidence_mix.values()):
        assert isinstance(value, int)


def test_no_float_appears_anywhere_in_the_projection():
    def walk(node):
        if isinstance(node, float):
            raise AssertionError("projection produced a score")
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        if isinstance(node, list):
            for v in node:
                walk(v)

    walk(project(build()).to_dict())


def test_luck_is_counted_separately_from_success():
    c = project(build())
    assert c.cells["attributable"] == 1
    assert c.cells["luck"] == 1


def test_evidence_mix_reports_classes_not_a_summary():
    c = project(build())
    assert c.evidence_mix == {"A": 1, "B": 0, "C": 0, "D": 1}


def test_completeness_is_full_when_declines_are_recorded():
    assert project(build()).completeness == "full"


def test_completeness_is_commitments_only_without_declines():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.commit(a_commitment("c-0"))
    assert project(sink.records).completeness == "commitments-only"


def test_completeness_is_partial_when_the_chain_has_a_gap():
    records = build()
    del records[1]
    assert project(records).completeness == "partial"
