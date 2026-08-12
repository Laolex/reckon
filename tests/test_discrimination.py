"""Discrimination: can the record separate a compliant run from a violating one.

The central case reproduces the OPA finding deliberately. That failure was found by
accident — identical input and bundle revision, opposite decisions, because config sat
outside the bundle roots. Here it is constructed on purpose, which is the whole point:
the claim stops being an anecdote and becomes a procedure anyone can run.
"""

from reckon.discrimination import discriminates


def test_a_record_that_cannot_separate_the_pair_reports_untestable():
    """The OPA shape. Every captured field is identical; the decision differs anyway.

    A reviewer checking this record finds nothing wrong, because nothing in it is
    wrong. The discriminating state — config resolved outside the bundle roots — was
    never captured, so the guarantee is untestable rather than merely unproven.
    """
    captured = {
        "input": {"user": "alice", "action": "deploy"},
        "policy": {"bundle_revision": "abc123"},
        "outcome": "admit",
        "recorded_at": "2026-08-12T10:00:00Z",
    }
    violating = dict(captured, outcome="admit", recorded_at="2026-08-12T11:00:00Z")

    result = discriminates(captured, violating, "the bundle revision decides the outcome")

    assert not result.separable
    assert result.identical
    assert not result.distinguishing
    rendered = result.render()
    assert "Testable:  NO" in rendered
    assert "never captured" in rendered
    assert "More logging at this level of detail cannot fix it." in rendered


def test_capturing_the_missing_field_makes_the_guarantee_testable():
    """The fix the tool implies: capture the state that actually decided it."""
    compliant = {
        "input": {"user": "alice"},
        "policy": {"bundle_revision": "abc123", "config_digest": "sha256:aaa"},
        "outcome": "admit",
    }
    violating = {
        "input": {"user": "alice"},
        "policy": {"bundle_revision": "abc123", "config_digest": "sha256:bbb"},
        "outcome": "reject",
    }

    result = discriminates(compliant, violating, "the bundle revision decides the outcome")

    assert result.separable
    assert "policy.config_digest" in result.distinguishing
    # `outcome` is the conclusion, not evidence for it — it is reported separately.
    assert "outcome" not in result.distinguishing
    assert result.conclusion_differs
    assert "Testable:  yes" in result.render()


def test_incidental_fields_alone_do_not_count_as_separation():
    """Timestamps differ between any two runs.

    Without this, every guarantee would report testable and the tool would be a
    generator of false assurance rather than a detector of missing evidence.
    """
    a = {"outcome": "admit", "recorded_at": "t0", "seq": 1, "prev_hash": "sha256:x"}
    b = {"outcome": "admit", "recorded_at": "t1", "seq": 2, "prev_hash": "sha256:y"}
    assert not discriminates(a, b, "g").separable


def test_a_field_present_in_only_one_run_is_separation():
    compliant = {"outcome": "admit", "approval": {"by": "human"}}
    violating = {"outcome": "admit"}
    result = discriminates(compliant, violating, "a human approved the action")
    assert result.separable
    assert "approval.by" in result.only_in_compliant


def test_nested_differences_are_reported_at_the_leaf():
    """Reporting `execution` as differing leaves the reader to go find out which part."""
    a = {"execution": {"runtime": "py3.11", "seed": 1, "path_digest": "sha256:a"}}
    b = {"execution": {"runtime": "py3.11", "seed": 1, "path_digest": "sha256:b"}}
    result = discriminates(a, b, "the code path is pinned")
    assert result.distinguishing == ["execution.path_digest"]
    assert "execution.runtime" in result.identical


def test_list_elements_are_addressed_by_index():
    a = {"candidates": [{"outcome": "admit"}, {"outcome": "reject"}]}
    b = {"candidates": [{"outcome": "admit"}, {"outcome": "admit"}]}
    result = discriminates(a, b, "every candidate is recorded")
    assert result.distinguishing == ["candidates[1].outcome"]


def test_to_dict_round_trips_the_finding():
    result = discriminates({"a": 1}, {"a": 2}, "g")
    payload = result.to_dict()
    assert payload["separable"] is True
    assert payload["guarantee"] == "g"
    assert payload["distinguishing"] == ["a"]


def test_the_conclusion_does_not_count_as_evidence():
    """Found by pointing this at dhdr's real admit/reject pairs.

    A record holding nothing but an input and an outcome, with identical inputs and
    opposite outcomes, proves nothing about why it flipped. The first version of this
    module reported it separable — the exact failure the module exists to detect,
    reintroduced inside the module.
    """
    a = {"input": {"x": 1}, "outcome": "admit"}
    b = {"input": {"x": 1}, "outcome": "reject"}
    r = discriminates(a, b, "the input decides the outcome")
    assert not r.separable
    assert r.conclusion_differs
    assert r.unexplained_flip
    assert "nothing" in r.render() and "accounts for" in r.render()


def test_an_unexplained_flip_is_a_stronger_finding_than_untestable():
    """Not 'we cannot tell' but 'the outcome changed and the record cannot say why'."""
    same = {"input": {"x": 1}, "outcome": "admit"}
    r = discriminates(same, dict(same), "g")
    assert not r.separable and not r.conclusion_differs and not r.unexplained_flip


def test_evidence_separation_survives_an_identical_conclusion():
    a = {"policy": {"revision": "949"}, "outcome": "admit"}
    b = {"policy": {"revision": "950"}, "outcome": "admit"}
    r = discriminates(a, b, "the revision is captured")
    assert r.separable
    assert not r.conclusion_differs
    assert r.distinguishing == ["policy.revision"]


def test_decision_id_and_ts_are_incidental():
    """Real dhdr records carry both, and neither says anything about a guarantee."""
    a = {"decision_id": "d-1", "ts": "t0", "reads": [{"digest": "sha256:a"}]}
    b = {"decision_id": "d-2", "ts": "t1", "reads": [{"digest": "sha256:a"}]}
    assert not discriminates(a, b, "g").separable
