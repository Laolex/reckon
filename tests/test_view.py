from reckon.commitment import Commitment, Obligation
from reckon.ledger import Ledger
from reckon.resolve import Resolution
from reckon.sink import MemorySink
from reckon.view import ledger_view


def a_commitment(cid, cls="B"):
    return Commitment(
        agent="helios-3",
        objective=f"objective {cid}",
        obligation=Obligation(statement=f"do {cid}", evidence_class=cls,
                              evidence_source="portal"),
        obligation_criteria="oc",
        outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z",
        sources=["s.example.org"],
        commitment_id=cid,
    )


def build():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.seal_only(a_commitment("c-0"))       # sealed then opened
    ledger.seal_only(a_commitment("c-1", "A"))  # sealed, never opened
    ledger.commit(a_commitment("c-2", "D"))     # written in the clear
    ledger.decline(reason="nothing qualified")
    ledger.reveal(a_commitment("c-0"))
    ledger.append(Resolution("c-0", "missed", "met", {"note": "market moved"}).to_dict())
    return sink.records


def test_a_revealed_commitment_knows_it_was_sealed_first():
    view = ledger_view(build())
    c0 = next(c for c in view.commitments if c.commitment_id == "c-0")
    assert c0.was_sealed_before_disclosure
    assert c0.sealed_seq == 0
    assert c0.disclosed_seq == 4


def test_a_clear_commitment_was_not_sealed_in_advance():
    view = ledger_view(build())
    c2 = next(c for c in view.commitments if c.commitment_id == "c-2")
    assert not c2.was_sealed_before_disclosure
    assert c2.sealed_seq is None


def test_unopened_seals_are_listed_without_disclosing_anything():
    view = ledger_view(build())
    assert len(view.unopened) == 1
    assert view.unopened[0].seq == 1
    assert view.unopened[0].seal.startswith("sha256:")


def test_resolution_is_attached_and_the_cell_is_derived():
    view = ledger_view(build())
    c0 = next(c for c in view.commitments if c.commitment_id == "c-0")
    assert c0.status == "resolved"
    assert c0.cell == "luck"
    assert c0.resolution["evidence_seen"] == {"note": "market moved"}


def test_open_commitments_are_the_ones_with_no_resolution():
    view = ledger_view(build())
    assert [c.commitment_id for c in view.open_commitments] == ["c-2"]


def test_declines_are_kept_as_part_of_the_record():
    assert len(ledger_view(build()).declines) == 1


def test_a_second_reveal_of_one_seal_cannot_also_claim_advance_sealing():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.seal_only(a_commitment("c-0"))
    ledger.reveal(a_commitment("c-0"))
    ledger.reveal(a_commitment("c-0"))
    first, second = ledger_view(sink.records).commitments
    assert first.was_sealed_before_disclosure
    assert not second.was_sealed_before_disclosure


def test_an_empty_ledger_views_cleanly():
    view = ledger_view([])
    assert view.agent == ""
    assert view.commitments == []
