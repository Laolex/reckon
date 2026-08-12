from reckon.commitment import Commitment, Obligation
from reckon.integrity import verify_ledger
from reckon.ledger import Ledger
from reckon.sink import MemorySink


def a_commitment(cid):
    return Commitment(
        agent="helios-3",
        objective="o",
        obligation=Obligation(statement="s", evidence_class="A", evidence_source="tx"),
        obligation_criteria="oc",
        outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z",
        sources=["s"],
        commitment_id=cid,
    )


def build(n=3):
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    for i in range(n):
        ledger.commit(a_commitment(f"c-{i}"))
    return sink.records


def test_intact_ledger_reports_intact():
    report = verify_ledger(build())
    assert report.intact
    assert report.gaps == []
    assert report.forks == []
    assert report.broken_seals == []


def test_a_missing_record_is_reported_as_a_gap():
    records = build(4)
    del records[2]
    report = verify_ledger(records)
    assert not report.intact
    assert report.gaps == [(1, 3)]


def test_an_edited_record_breaks_the_chain():
    records = build()
    records[0]["objective"] = "tampered"
    report = verify_ledger(records)
    assert not report.intact
    assert report.forks == [1]


def test_an_edited_sealed_field_breaks_the_seal():
    records = build()
    records[1]["outcome_criteria"] = "tampered"
    report = verify_ledger(records)
    assert not report.intact
    assert "c-1" in report.broken_seals


def test_render_names_the_specific_failure():
    records = build(4)
    del records[2]
    assert "gap" in verify_ledger(records).render().lower()
