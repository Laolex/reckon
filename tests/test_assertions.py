"""The assertion grammar, and specifically its refusals.

A grammar whose rejection path never fires accepts everything, so most of these
tests are about what it declines rather than what it admits.
"""

import pytest

from reckon.assertions import (
    Form,
    UncertifiableAssertion,
    certify,
    parse,
)


def test_recorded_facts_parse_and_certify():
    assert parse("the input was {user: alice}").form is Form.RECORDED_INPUT
    assert parse("the outcome was admit").form is Form.RECORDED_OUTCOME
    assert parse("policy max_amount resolved to 9000").form is Form.RECORDED_RESOLUTION
    for text in (
        "the input was x",
        "the outcome was admit",
        "policy k resolved to 1",
    ):
        assert certify(text).certifiable


def test_a_deterministic_counterfactual_is_certifiable():
    a = parse("without the gate the outcome would be admit")
    assert a.form is Form.DETERMINISTIC_COUNTERFACTUAL
    assert a.max_class == "C2"
    assert certify("without the gate the outcome would be admit")


def test_a_state_coupled_counterfactual_parses_but_never_certifies():
    """The claim this module exists for. Sayable, and permanently unsupportable."""
    a = parse("with the gate off this would have been profitable")
    assert a.form is Form.STATE_COUPLED_COUNTERFACTUAL
    assert a.max_class == "C3"
    assert not a.certifiable
    assert "evidence ends and hypothesis begins" in a.render()

    with pytest.raises(UncertifiableAssertion) as excinfo:
        certify("with the gate off this would have been profitable")
    assert "NOT certifiable" in str(excinfo.value)


def test_state_coupled_is_matched_before_plain_counterfactual():
    """Ordering is load-bearing.

    If the deterministic pattern were tried first, a profit claim would match as an
    ordinary counterfactual and be certified at C2 — the exact substitution the
    grammar exists to prevent.
    """
    for text in (
        "without the gate the outcome would have been profitable",
        "under the old policy revenue would have been higher",
        "with more retries the user would have converted",
    ):
        assert parse(text).form is Form.STATE_COUPLED_COUNTERFACTUAL


def test_an_unexpressible_assertion_is_refused_before_any_verification():
    with pytest.raises(UncertifiableAssertion) as excinfo:
        parse("the agent seemed confident about this one")
    message = str(excinfo.value)
    assert "no assertion form matches" in message
    assert "Expressible forms" in message
    assert "refused here" in message


def test_every_form_has_a_maximum_class():
    from reckon.assertions import MAX_CLASS

    assert set(MAX_CLASS) == set(Form)


def test_every_form_is_reachable_from_some_text():
    """A form no pattern can produce is documentation, not grammar."""
    reachable = {
        parse("the input was x").form,
        parse("the outcome was admit").form,
        parse("policy k resolved to 1").form,
        parse("without the gate the outcome would be reject").form,
        parse("this would have been profitable").form,
    }
    assert reachable == set(Form)
