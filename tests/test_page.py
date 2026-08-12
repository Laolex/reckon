from reckon.commitment import Commitment, Obligation
from reckon.credential import project
from reckon.ledger import Ledger
from reckon.page import render
from reckon.resolve import Resolution
from reckon.sink import MemorySink


def build(broken=False):
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    ledger.commit(Commitment(
        agent="helios-3", objective="o",
        obligation=Obligation(statement="s", evidence_class="A", evidence_source="tx"),
        obligation_criteria="oc", outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z", sources=["s"], commitment_id="c-0",
    ))
    ledger.decline(reason="nothing qualified")
    ledger.append(Resolution("c-0", "missed", "met", {"note": "market moved"}).to_dict())
    records = sink.records
    if broken:
        del records[1]
    return project(records)


def test_page_names_the_cells_in_plain_words():
    html = render(build())
    assert "Luck" in html
    assert "obligation" in html.lower()
    assert "outcome" in html.lower()


def test_page_escapes_agent_names():
    credential = build()
    credential.agent = "<script>alert(1)</script>"
    assert "<script>" not in render(credential)


def test_a_broken_record_reports_no_figures():
    html = render(build(broken=True))
    assert "unreportable" in html.lower()
    assert "gap" in html.lower()


def test_a_broken_record_publishes_none_of_the_credential_figures():
    """A number beside a warning is still a number, and readers keep the number."""
    html = render(build(broken=True))
    for label in ("Commitments on the record", "Declined openly", "Resolved",
                  "Sealed, never opened", "Class A", "Luck"):
        assert label not in html, label


def test_evidence_classes_are_shown_as_a_mix():
    html = render(build())
    assert "Class A" in html
    assert "Class D" in html
