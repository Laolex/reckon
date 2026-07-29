import pytest

from reckon.resolve import Resolution, cell_for


def test_the_four_clean_cells():
    assert cell_for("met", "met") == "attributable"
    assert cell_for("met", "missed") == "competent_unsuccessful"
    assert cell_for("missed", "met") == "luck"
    assert cell_for("missed", "missed") == "failure"


def test_ambiguity_never_gets_forced_into_a_corner():
    assert cell_for("ambiguous", "met") == "indeterminate"
    assert cell_for("met", "ambiguous") == "indeterminate"
    assert cell_for("unresolvable", "missed") == "indeterminate"


def test_unknown_verdict_is_refused():
    with pytest.raises(ValueError, match="verdict"):
        cell_for("probably", "met")


def test_resolution_to_dict_carries_its_inputs():
    r = Resolution(
        commitment_id="c-1",
        obligation_verdict="met",
        outcome_verdict="missed",
        evidence_seen={"portal": "12 confirmations"},
    )
    d = r.to_dict()
    assert d["kind"] == "resolution"
    assert d["cell"] == "competent_unsuccessful"
    assert d["evidence_seen"] == {"portal": "12 confirmations"}


def test_resolution_requires_evidence_it_actually_saw():
    with pytest.raises(ValueError, match="evidence_seen"):
        Resolution(
            commitment_id="c-1",
            obligation_verdict="met",
            outcome_verdict="met",
            evidence_seen={},
        )
