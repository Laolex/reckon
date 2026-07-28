"""The ablation is a claim about the format, so it is checked like one."""

from demo.ablation import ABLATIONS, complete_record, delete, highest_class, run


def test_the_baseline_supports_c2():
    assert highest_class(complete_record()) == "C2"


def test_every_c0_and_c1_field_is_load_bearing():
    """If deleting a field changes nothing, it is decoration and should be cut."""
    results = dict(run())
    for path in (
        "execution.runtime",
        "execution.deps_digest",
        "execution.path_digest",
        "predicate.id",
        "compared.value",
        "policy.resolved_value",
        "policy.resolution.provenance",
        "candidates.completeness",
        "candidates.items",
    ):
        assert results[path] != "C2", f"{path} does not earn its place"


def test_the_decorative_fields_are_exactly_the_ones_we_admit_to():
    """Named explicitly, so adding a field without justifying it fails here."""
    decorative = {path for path, available in run() if available == "C2"}
    assert decorative == {"action.params_digest", "capture.sdk_version", "ts"}


def test_deleting_a_field_never_raises_the_class():
    """Demotion only. Removing evidence cannot make a record claim more."""
    baseline = highest_class(complete_record())
    order = [None, "C0", "C1", "C2"]
    for path in ABLATIONS:
        ablated = highest_class(delete(complete_record(), path))
        assert order.index(ablated) <= order.index(baseline)
