"""Commit-reveal: seal time is not visibility time.

The seal binds the claim before the outcome is known; the reveal opens it later. The
attack this invites is obvious — seal ten, open the two that worked. It is closed by
counting the seals that were never opened, which is why `unopened` is a first-class
figure on the credential rather than a diagnostic.
"""

import pytest

from reckon.commitment import Commitment, Obligation
from reckon.credential import project
from reckon.integrity import verify_ledger
from reckon.ledger import Ledger
from reckon.page import render
from reckon.sink import MemorySink


def a_commitment(cid, cls="B"):
    return Commitment(
        agent="helios-3",
        objective=f"objective for {cid}",
        obligation=Obligation(statement="s", evidence_class=cls, evidence_source="src"),
        obligation_criteria="oc",
        outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z",
        sources=["s"],
        commitment_id=cid,
    )


def test_a_sealed_commitment_discloses_nothing_but_its_seal_and_its_time():
    sink = MemorySink()
    Ledger(sink, agent="helios-3").seal_only(a_commitment("c-0"))
    record = sink.records[0]
    assert record["kind"] == "sealed_commitment"
    assert record["seal"].startswith("sha256:")
    assert set(record) == {"kind", "seal", "agent", "seq", "prev_hash", "recorded_at"}


def test_the_reveal_matches_the_seal_that_was_written_earlier():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    commitment = a_commitment("c-0")
    ledger.seal_only(commitment)
    ledger.reveal(commitment)
    sealed, revealed = sink.records
    assert revealed["kind"] == "reveal"
    assert revealed["seal"] == sealed["seal"]
    assert verify_ledger(sink.records).intact


def test_revealing_something_different_from_what_was_sealed_is_caught():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.seal_only(a_commitment("c-0"))
    ledger.reveal(a_commitment("c-0", cls="D"))  # same id, different obligation
    report = verify_ledger(sink.records)
    assert not report.intact
    assert report.unmatched_reveals == ["c-0"]
    assert "reveal" in report.render().lower()


def test_opening_the_same_seal_twice_is_caught():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    commitment = a_commitment("c-0")
    ledger.seal_only(commitment)
    ledger.reveal(commitment)
    ledger.reveal(commitment)
    assert verify_ledger(sink.records).unmatched_reveals == ["c-0"]


def test_a_reveal_cannot_predate_its_seal():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    commitment = a_commitment("c-0")
    ledger.reveal(commitment)
    ledger.seal_only(commitment)
    assert verify_ledger(sink.records).unmatched_reveals == ["c-0"]


def test_editing_a_revealed_field_breaks_its_seal():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    commitment = a_commitment("c-0")
    ledger.seal_only(commitment)
    ledger.reveal(commitment)
    sink.records[1]["outcome_criteria"] = "tampered"
    assert "c-0" in verify_ledger(sink.records).broken_seals


def test_unopened_seals_are_counted_on_the_credential():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    for i in range(5):
        ledger.seal_only(a_commitment(f"c-{i}"))
    ledger.reveal(a_commitment("c-0"))
    ledger.reveal(a_commitment("c-1"))
    c = project(sink.records)
    assert c.sealed == 5
    assert c.revealed == 2
    assert c.unopened == 3
    assert c.commitments == 2  # only opened commitments can be classified


def test_the_unopened_count_is_on_the_page():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.seal_only(a_commitment("c-0"))
    ledger.seal_only(a_commitment("c-1"))
    ledger.reveal(a_commitment("c-0"))
    ledger.decline(reason="nothing else qualified")
    html = render(project(sink.records))
    assert "never opened" in html.lower()


def test_reveal_refuses_a_commitment_from_another_agent():
    with pytest.raises(ValueError, match="helios-3"):
        Ledger(MemorySink(), agent="selene-1").reveal(a_commitment("c-0"))
