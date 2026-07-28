"""Emitter tests. Every assertion here traces to a requirement in docs/RCDR-v0.1.md."""

import json

from reckon import JsonlSink, Recorder
from reckon.predicate import predicate_id


def recorder(tmp_path, **kwargs):
    sink = JsonlSink(tmp_path / "decisions.jsonl")
    return Recorder(sink=sink, run_id="r-88", emitter="test", **kwargs), sink


def read(tmp_path):
    lines = (tmp_path / "decisions.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


# --- predicate identity (§4.2) -------------------------------------------------


def test_predicate_id_is_structural_not_positional():
    """LangGraph's gates were indistinguishable in the record. Structure separates them."""
    a = predicate_id("gte", "request.amount", "policy.limit")
    b = predicate_id("gte", "request.amount", "policy.limit")
    c = predicate_id("gte", "request.size", "policy.limit")
    d = predicate_id("lt", "request.amount", "policy.limit")
    assert a == b
    assert a != c
    assert a != d
    assert a.startswith("p:")


# --- the basic crossing --------------------------------------------------------


def test_decision_records_predicate_compared_value_and_policy(tmp_path):
    rec, _ = recorder(tmp_path)
    with rec.decision(action="transfer") as d:
        d.policy("policy.limit", value=5000, provenance="bundled", source="opa:bundle")
        allowed = d.check("gte", left="request.amount", value=4200, right="policy.limit")
        d.reject() if not allowed else d.admit()

    record = read(tmp_path)[0]
    assert record["rcdr_version"] == "0.1"
    assert record["predicate"]["operator"] == "gte"
    assert record["compared"]["value"] == 4200
    assert record["policy"]["resolved_value"] == 5000
    assert record["policy"]["resolution"]["provenance"] == "bundled"
    assert record["outcome"] == "reject"
    assert record["action"]["id"] == "transfer"


def test_check_returns_the_real_boolean(tmp_path):
    rec, _ = recorder(tmp_path)
    with rec.decision(action="transfer") as d:
        d.policy("policy.limit", value=100, provenance="bundled", source="s")
        assert d.check("gte", left="x", value=200, right="policy.limit") is True
        d.admit()


def test_sequence_increments_within_a_run(tmp_path):
    rec, _ = recorder(tmp_path)
    for _ in range(3):
        with rec.decision(action="a") as d:
            d.policy("k", value=1, provenance="bundled", source="s")
            d.check("gte", left="x", value=1, right="k")
            d.admit()
    assert [r["sequence"] for r in read(tmp_path)] == [0, 1, 2]


# --- provenance honesty (§4.4) -------------------------------------------------


def test_unknown_provenance_is_recorded_not_suppressed(tmp_path):
    """The OPA failure was undetectable. The record must admit its own ignorance."""
    rec, _ = recorder(tmp_path)
    with rec.decision(action="transfer") as d:
        d.policy("policy.limit", value=5000, provenance="unknown", source="opa:data-api")
        d.check("gte", left="request.amount", value=4200, right="policy.limit")
        d.reject()

    assert read(tmp_path)[0]["policy"]["resolution"]["provenance"] == "unknown"


def test_invalid_provenance_is_refused():
    import pytest

    from reckon.record import Policy

    with pytest.raises(ValueError, match="provenance"):
        Policy(key="k", resolved_value=1, provenance="probably-fine", source="s")


# --- survivorship (§4.6) -------------------------------------------------------


def test_absent_candidates_default_to_taken_only(tmp_path):
    """Polymarket is taken-only and nothing says so. Here it says so."""
    rec, _ = recorder(tmp_path)
    with rec.decision(action="transfer") as d:
        d.policy("k", value=1, provenance="bundled", source="s")
        d.check("gte", left="x", value=1, right="k")
        d.admit()

    assert read(tmp_path)[0]["candidates"]["completeness"] == "taken_only"


def test_candidates_can_be_declared_exhaustive(tmp_path):
    rec, _ = recorder(tmp_path)
    with rec.decision(action="transfer") as d:
        d.policy("k", value=100, provenance="bundled", source="s")
        d.candidate("transfer", compared_value=200, outcome="admit", predicate="p:x")
        d.candidate("hold", compared_value=50, outcome="reject", predicate="p:x")
        d.candidates_exhaustive()
        d.check("gte", left="x", value=200, right="k")
        d.admit()

    candidates = read(tmp_path)[0]["candidates"]
    assert candidates["completeness"] == "exhaustive"
    assert len(candidates["items"]) == 2
    assert candidates["items"][1]["compared_value"] == 50


# --- execution model (§4.8) ----------------------------------------------------


def test_execution_model_is_captured(tmp_path):
    rec, _ = recorder(tmp_path)
    with rec.decision(action="a", pure=True) as d:
        d.policy("k", value=1, provenance="bundled", source="s")
        d.check("gte", left="x", value=1, right="k")
        d.admit()

    execution = read(tmp_path)[0]["execution"]
    assert execution["runtime"].startswith("python3")
    assert execution["deps_digest"].startswith("sha256:")
    assert execution["path_digest"].startswith("sha256:")
    assert execution["pure"] is True


def test_path_digest_changes_with_resolution_source(tmp_path):
    """Non-compositionality: identical components, different path."""
    rec_a, _ = recorder(tmp_path / "a")
    with rec_a.decision(action="a") as d:
        d.policy("k", value=1, provenance="bundled", source="opa:bundle")
        d.check("gte", left="x", value=1, right="k")
        d.admit()

    rec_b, _ = recorder(tmp_path / "b")
    with rec_b.decision(action="a") as d:
        d.policy("k", value=1, provenance="runtime_override", source="opa:data-api")
        d.check("gte", left="x", value=1, right="k")
        d.admit()

    a = read(tmp_path / "a")[0]["execution"]
    b = read(tmp_path / "b")[0]["execution"]
    assert a["deps_digest"] == b["deps_digest"]
    assert a["path_digest"] != b["path_digest"]


# --- emitter refuses to guess --------------------------------------------------


def test_check_without_a_registered_policy_is_refused(tmp_path):
    import pytest

    rec, _ = recorder(tmp_path)
    with pytest.raises(ValueError, match="not registered"):
        with rec.decision(action="a") as d:
            d.check("gte", left="x", value=1, right="never.registered")


def test_decision_without_an_outcome_is_refused(tmp_path):
    import pytest

    rec, _ = recorder(tmp_path)
    with pytest.raises(ValueError, match="outcome"):
        with rec.decision(action="a") as d:
            d.policy("k", value=1, provenance="bundled", source="s")
            d.check("gte", left="x", value=1, right="k")
