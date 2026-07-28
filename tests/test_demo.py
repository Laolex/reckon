"""The demo's claims are tested, not narrated.

If the before/after arc is the pitch, then a regression in it is a regression in the
pitch. These assert the three things the demo actually claims.
"""

from demo.opa_replay import as_rcdr, load_opa_decisions, after
from reckon import verify_run


def test_the_probe_log_contains_a_real_contradiction():
    """Identical input and revision, opposite results. This is the whole premise."""
    entries = load_opa_decisions()
    assert len(entries) == 2
    first, second = entries
    assert first["input"] == second["input"]
    assert first["bundles"]["authz"]["revision"] == second["bundles"]["authz"]["revision"]
    assert first["labels"]["version"] == second["labels"]["version"]
    assert first["result"]["action"] != second["result"]["action"]


def test_before_the_opa_log_cannot_support_c1():
    records = [as_rcdr(entry, index) for index, entry in enumerate(load_opa_decisions())]
    report = verify_run(records, requested="C1")
    assert report.satisfied is False
    assert report.available != "C1"


def test_after_the_reemitted_run_supports_c2(capsys):
    records = after()
    capsys.readouterr()
    assert verify_run(records, requested="C2").satisfied is True


def test_after_the_two_decisions_are_distinguishable(capsys):
    """What the bundle revision could not do, the path digest does."""
    records = after()
    capsys.readouterr()
    assert records[0]["execution"]["path_digest"] != records[1]["execution"]["path_digest"]
    assert records[0]["policy"]["resolved_value"] != records[1]["policy"]["resolved_value"]
    assert records[0]["outcome"] != records[1]["outcome"]
