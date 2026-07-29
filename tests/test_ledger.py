import pytest

from reckon.commitment import Commitment, Obligation
from reckon.ledger import GENESIS_HASH, Ledger, read
from reckon.record import digest
from reckon.sink import MemorySink


def a_commitment(cid="c-1"):
    return Commitment(
        agent="helios-3",
        objective="increase treasury yield",
        obligation=Obligation(
            statement="submit 10 applications",
            evidence_class="B",
            evidence_source="portal confirmations",
        ),
        obligation_criteria="10 or more confirmed",
        outcome_criteria="one award",
        horizon="2026-09-01T00:00:00Z",
        sources=["grants.example.org"],
        commitment_id=cid,
    )


def test_sequence_starts_at_zero_and_increments_by_one():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.commit(a_commitment("c-1"))
    ledger.decline(reason="no qualifying grants open")
    ledger.commit(a_commitment("c-2"))
    assert [r["seq"] for r in sink.records] == [0, 1, 2]


def test_first_record_links_to_genesis_and_the_rest_chain():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.commit(a_commitment("c-1"))
    ledger.decline(reason="nothing qualified")
    first, second = sink.records
    assert first["prev_hash"] == GENESIS_HASH
    assert second["prev_hash"] == digest(first)


def test_decline_is_a_first_class_record():
    sink = MemorySink()
    Ledger(sink, agent="helios-3").decline(reason="nothing qualified")
    assert sink.records[0]["kind"] == "decline"
    assert sink.records[0]["reason"] == "nothing qualified"


def test_decline_requires_a_reason():
    with pytest.raises(ValueError, match="reason"):
        Ledger(MemorySink(), agent="helios-3").decline(reason="")


def test_commitment_from_another_agent_is_refused():
    with pytest.raises(ValueError, match="helios-3"):
        Ledger(MemorySink(), agent="selene-1").commit(a_commitment("c-1"))


def test_read_round_trips_through_a_file(tmp_path):
    from reckon.sink import JsonlSink

    path = tmp_path / "helios-3.jsonl"
    ledger = Ledger(JsonlSink(path), agent="helios-3")
    ledger.commit(a_commitment("c-1"))
    ledger.decline(reason="nothing qualified")
    records = read(str(path))
    assert [r["seq"] for r in records] == [0, 1]
    assert records[0]["commitment_id"] == "c-1"
