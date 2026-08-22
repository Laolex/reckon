import json

from reckon.investigate import compare_records, project_graph, project_record
from reckon.investigation_site import render


def decision(
    decision_id: str,
    *,
    sequence: int = 0,
    value: int = 4200,
    outcome: str = "admit",
    reads=(),
    writes=(),
):
    return {
        "rcdr_version": "0.1",
        "decision_id": decision_id,
        "run_id": "run-1",
        "sequence": sequence,
        "ts": "2026-08-21T00:00:00Z",
        "outcome": outcome,
        "action": {"id": "approve-transfer", "params_digest": "sha256:params"},
        "candidates": {
            "completeness": "exhaustive",
            "items": [
                {
                    "action_id": "approve-transfer",
                    "compared_value": value,
                    "outcome": outcome,
                    "predicate_id": "transfer-under-limit",
                }
            ],
        },
        "reads": [
            {"key": key, "value_digest": "sha256:read", "source": "store"}
            for key in reads
        ],
        "writes": [{"key": key, "value_digest": "sha256:write"} for key in writes],
        "execution": {
            "runtime": "python:3.12",
            "deps_digest": "sha256:deps",
            "path_digest": "sha256:path",
            "seed": None,
            "clock": None,
            "pure": True,
        },
        "capture": {"sdk_version": "0.1.1", "emitter": "test"},
        "predicate": {
            "id": "transfer-under-limit",
            "operator": "lt",
            "expression": "amount < policy.transfer_limit",
        },
        "compared": {"value": value, "type": "int"},
        "policy": {
            "key": "policy.transfer_limit",
            "resolved_value": 5000,
            "resolution": {
                "provenance": "bundled",
                "source": "opa:payments",
                "revision": "bundle-9",
            },
        },
    }


def test_projection_is_deterministic_and_uses_only_canonical_fields():
    record = decision("d-1")
    first = project_record(record, source_ref="run.jsonl")
    second = project_record(json.loads(json.dumps(record)), source_ref="run.jsonl")
    assert first == second
    assert first.projection_id == first.record_digest
    assert first.capability_class == "C2"
    assert "transfer-under-limit" in first.search_text
    assert not hasattr(first, "relation_label")


def test_graph_projection_deduplicates_entities_and_derives_state_edges():
    records = [
        decision("d-1", sequence=0, writes=("risk.limit",)),
        decision("d-2", sequence=1, reads=("risk.limit",), value=6200, outcome="reject"),
    ]
    first = project_graph(records, source_ref="run.jsonl")
    second = project_graph(records, source_ref="run.jsonl")
    assert first == second
    assert len({node.projection_id for node in first.nodes}) == len(first.nodes)
    coupling = [edge for edge in first.edges if edge.label == "STATE_COUPLES"]
    assert len(coupling) == 1
    assert coupling[0].properties == {"key": "risk.limit"}


def test_compare_names_first_structural_evidence_not_outcome():
    left = decision("d-left", value=4200, outcome="admit")
    right = decision("d-right", value=6200, outcome="reject")
    result = compare_records(left, right, guarantee="transfer remains under policy limit")
    assert result.outcome_changed is True
    assert result.explained is True
    assert result.first_evidence_divergence == "compared.value"
    assert result.left_capability.available == "C2"
    assert result.right_capability.available == "C2"


def test_compare_calls_an_outcome_only_change_unexplained():
    left = decision("d-left", outcome="admit")
    right = decision("d-right", outcome="reject")
    right["candidates"]["items"][0]["outcome"] = "admit"
    result = compare_records(left, right, guarantee="same evidence produces same result")
    assert result.outcome_changed is True
    assert result.explained is False
    assert result.first_evidence_divergence is None
    assert result.discrimination.unexplained_flip is True


def test_proof_screen_escapes_record_values_and_marks_c3_boundary():
    left = decision("<script>alert(1)</script>", writes=("risk.limit",))
    right = decision("d-right", value=6200, outcome="reject")
    result = compare_records(left, right, guarantee="safe < transfer", left_run=[left])
    page = render(result)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "safe &lt; transfer" in page
    assert "C3 is never certified" in page


def test_proof_screen_stages_the_argument_as_accessible_evidence_ui():
    left = decision("d-left", value=4200, outcome="admit")
    right = decision("d-right", value=6200, outcome="reject")
    result = compare_records(left, right, guarantee="transfer remains under policy limit")

    page = render(result)

    assert 'aria-label="Verification sequence"' in page
    assert "Candidate nominated" in page
    assert "Canonical records reopened" in page
    assert "Capability boundary enforced" in page
    assert 'aria-label="Evidence scope"' in page
    assert "Evidence supports" in page
    assert "Evidence does not support" in page
    assert '<table class="evidence-table">' in page
    assert '<th scope="row">' in page


def test_unexplained_flip_is_marked_for_attention_without_inventing_evidence():
    left = decision("d-left", outcome="admit")
    right = decision("d-right", outcome="reject")
    right["candidates"]["items"][0]["outcome"] = "admit"
    result = compare_records(left, right, guarantee="same evidence produces same result")

    page = render(result)

    assert "No evidence difference found" in page
    assert '<span class="step-state attention">attention</span>' in page
    assert "no captured field explains it" in page
