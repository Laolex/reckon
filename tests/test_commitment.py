import pytest

from reckon.commitment import Commitment, Obligation


def make(**over):
    kwargs = dict(
        agent="helios-3",
        objective="increase treasury yield",
        obligation=Obligation(
            statement="submit 10 qualifying grant applications",
            evidence_class="B",
            evidence_source="grants.example.org confirmation emails",
        ),
        obligation_criteria="10 or more submissions confirmed by the portal",
        outcome_criteria="at least one award granted",
        horizon="2026-09-01T00:00:00Z",
        sources=["grants.example.org"],
        commitment_id="c-0001",
    )
    kwargs.update(over)
    return Commitment(**kwargs)


def test_seal_is_stable_and_covers_every_sealed_field():
    assert make().seal() == make().seal()
    for field, value in [
        ("objective", "something else"),
        ("obligation_criteria", "5 or more"),
        ("outcome_criteria", "two awards"),
        ("horizon", "2026-10-01T00:00:00Z"),
        ("sources", ["other.example.org"]),
    ]:
        assert make(**{field: value}).seal() != make().seal(), field


def test_changing_the_obligation_changes_the_seal():
    other = Obligation(
        statement="submit 3 applications",
        evidence_class="B",
        evidence_source="grants.example.org confirmation emails",
    )
    assert make(obligation=other).seal() != make().seal()


def test_missing_criteria_is_refused_not_defaulted():
    with pytest.raises(ValueError, match="obligation_criteria"):
        make(obligation_criteria="")


def test_missing_obligation_is_refused():
    with pytest.raises(ValueError, match="obligation"):
        make(obligation=None)


def test_unknown_evidence_class_is_refused():
    with pytest.raises(ValueError, match="evidence_class"):
        Obligation(statement="x", evidence_class="Z", evidence_source="y")


def test_to_dict_shape():
    d = make().to_dict()
    assert d["kind"] == "commitment"
    assert d["agent"] == "helios-3"
    assert d["obligation"]["evidence_class"] == "B"
    assert d["seal"].startswith("sha256:")
