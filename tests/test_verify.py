"""Verifier tests. §5.1 class computation and §5.2 rules."""

import json

from reckon import JsonlSink, Recorder
from reckon.verify import verify


def build(tmp_path, provenance="bundled", exhaustive=False, pure=True, candidate_values=True):
    sink = JsonlSink(tmp_path / "d.jsonl")
    rec = Recorder(sink=sink, run_id="r-1", emitter="test")
    with rec.decision(action="transfer", pure=pure) as d:
        d.policy("policy.limit", value=5000, provenance=provenance, source="opa:bundle")
        if exhaustive:
            d.candidate(
                "transfer",
                compared_value=4200 if candidate_values else None,
                outcome="reject",
                predicate="p:x",
            )
            d.candidates_exhaustive()
        d.check("gte", left="request.amount", value=4200, right="policy.limit")
        d.reject()
    return json.loads((tmp_path / "d.jsonl").read_text().splitlines()[0])


def test_complete_record_supports_c2(tmp_path):
    report = verify(build(tmp_path, exhaustive=True), requested="C2")
    assert report.available == "C2"
    assert report.satisfied is True
    assert report.missing == []


def test_taken_only_record_stops_at_c1(tmp_path):
    report = verify(build(tmp_path), requested="C2")
    assert report.available == "C1"
    assert report.satisfied is False
    assert "candidates.completeness = exhaustive" in report.missing


def test_unknown_provenance_caps_at_c0(tmp_path):
    """The whole point of the format (§8)."""
    report = verify(build(tmp_path, provenance="unknown"), requested="C1")
    assert report.available == "C0"
    assert report.satisfied is False
    assert "policy.resolution.provenance != unknown" in report.missing


def test_candidate_without_compared_value_fails_c2(tmp_path):
    report = verify(
        build(tmp_path, exhaustive=True, candidate_values=False), requested="C2"
    )
    assert report.available == "C1"
    assert "candidates.items[].compared_value" in report.missing


def test_impure_decision_without_a_seed_fails_c0(tmp_path):
    report = verify(build(tmp_path, pure=False), requested="C0")
    assert report.available is None
    assert "execution.seed" in report.missing


def test_report_never_carries_a_score(tmp_path):
    report = verify(build(tmp_path), requested="C2")
    rendered = report.render()
    for banned in ("%", "score", "confidence", "0.", "probability"):
        assert banned not in rendered.lower()


def test_report_renders_type_error_shape(tmp_path):
    rendered = verify(build(tmp_path), requested="C2").render()
    assert "Requested: Loosening Replay (C2)" in rendered
    assert "Available: C1" in rendered
    assert "Missing:" in rendered


def test_c3_is_never_certified(tmp_path):
    report = verify(build(tmp_path, exhaustive=True), requested="C3")
    assert report.satisfied is False
    assert report.available == "C2"
    assert any("not certifiable" in m for m in report.missing)
