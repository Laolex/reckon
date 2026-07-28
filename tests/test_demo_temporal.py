"""The Temporal arc's claims.

Temporal is the case a skeptic will raise, so these are the assertions that have to hold.
"""

from demo.temporal_replay import (
    absent,
    after,
    as_rcdr,
    component_identity,
    findings,
)
from reckon import verify_run


def test_both_cases_recorded_a_trade_and_replayed_a_skip():
    """Identical divergence in both cases. Only the detection differs."""
    data = findings()
    for case in ("A", "B"):
        assert data[case]["result"]["action"] == "trade"
        assert data[case]["replay_decided"] == "skip"


def test_the_command_boundary_is_what_decides_detection():
    data = findings()
    assert "NondeterminismError" in data["A"]["replay"]
    assert "REPLAY SUCCEEDED" in data["B"]["replay"]


def test_the_deciding_value_is_absent_from_both_histories():
    for case in ("A", "B"):
        assert set(absent(case).values()) == {0}


def test_the_component_checksum_does_not_distinguish_the_runs():
    """A component version is not a path digest — the same claim OPA's revision failed."""
    a, b = component_identity("A"), component_identity("B")
    assert a["binaryChecksum"] and a["binaryChecksum"] == b["binaryChecksum"]


def test_before_the_history_cannot_support_c1():
    records = [as_rcdr("A", 0), as_rcdr("B", 1)]
    report = verify_run(records, requested="C1")
    assert report.satisfied is False
    assert report.available is None


def test_after_the_reemitted_run_supports_c2(capsys):
    records = after()
    capsys.readouterr()
    assert verify_run(records, requested="C2").satisfied is True


def test_after_the_two_evaluations_disagree_without_replay(capsys):
    """The point: detecting the divergence no longer requires re-executing anything."""
    records = after()
    capsys.readouterr()
    assert records[0]["outcome"] != records[1]["outcome"]
    assert records[0]["policy"]["resolved_value"] != records[1]["policy"]["resolved_value"]
    assert records[0]["compared"]["value"] == records[1]["compared"]["value"]
