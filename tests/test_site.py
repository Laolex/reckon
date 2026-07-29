import json
import re

import pytest

from reckon.commitment import Commitment, Obligation
from reckon.ledger import Ledger
from reckon.resolve import Resolution
from reckon.sink import JsonlSink
from reckon.site import _slug, build


def a_commitment(agent, cid, cls="B"):
    return Commitment(
        agent=agent,
        objective=f"objective {cid}",
        obligation=Obligation(statement=f"do {cid}", evidence_class=cls,
                              evidence_source="portal confirmations"),
        obligation_criteria="10 or more confirmed",
        outcome_criteria="at least one award",
        horizon="2026-09-01T00:00:00Z",
        sources=["s.example.org"],
        commitment_id=cid,
    )


@pytest.fixture
def ledgers(tmp_path):
    d = tmp_path / "ledgers"
    d.mkdir()

    ledger = Ledger(JsonlSink(d / "helios-3.jsonl"), agent="helios-3")
    ledger.seal_only(a_commitment("helios-3", "c-0"))
    ledger.seal_only(a_commitment("helios-3", "c-1", "A"))
    ledger.decline(reason="nothing qualified in week 31")
    ledger.reveal(a_commitment("helios-3", "c-0"))
    ledger.append(Resolution("c-0", "missed", "met", {"note": "market moved"}).to_dict())

    # A second agent whose record has a hole punched in it.
    broken_path = d / "selene-1.jsonl"
    other = Ledger(JsonlSink(broken_path), agent="selene-1")
    other.commit(a_commitment("selene-1", "s-0", "D"))
    other.commit(a_commitment("selene-1", "s-1"))
    other.commit(a_commitment("selene-1", "s-2"))
    lines = broken_path.read_text().splitlines()
    broken_path.write_text("\n".join([lines[0], lines[2]]) + "\n")

    return d


def build_site(ledgers, tmp_path):
    out = tmp_path / "site"
    build(str(ledgers), str(out))
    return out


def read(out, rel):
    return (out / rel).read_text(encoding="utf-8")


def test_every_expected_page_is_written(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    for rel in [
        "index.html", "open.html", "verify.html",
        "launch.html", "feed.html", "standings.html",
        "assets/site.css", "assets/verify.js", "assets/verify-ui.js",
        "a/helios-3/index.html", "a/helios-3/ledger.html",
        "a/helios-3/helios-3.jsonl", "a/helios-3/c/c-0.html",
        "a/selene-1/index.html",
    ]:
        assert (out / rel).exists(), rel


def test_the_published_raw_ledger_still_verifies(ledgers, tmp_path):
    """The download must be the record, not a rendering of it."""
    from reckon.integrity import verify_ledger

    out = build_site(ledgers, tmp_path)
    records = [json.loads(l) for l in read(out, "a/helios-3/helios-3.jsonl").splitlines()]
    assert verify_ledger(records).intact


def test_a_broken_record_publishes_no_counts(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    page = read(out, "a/selene-1/index.html")
    assert "unreportable" in page.lower()
    for label in ("Commitments", "Declined openly", "Sealed, never opened"):
        assert label not in page, label


def test_an_intact_record_publishes_its_counts(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    page = read(out, "a/helios-3/index.html")
    assert "Record intact" in page
    assert "Sealed, never opened" in page
    assert "Luck" in page


def test_no_page_contains_a_rate_or_a_percentage(ledgers, tmp_path):
    """Design law: counts and classes, never a score."""
    out = build_site(ledgers, tmp_path)
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "%" not in text, path
        # A decimal between digits would be a rate; hashes and dates are not.
        for match in re.finditer(r"\d+\.\d+", text):
            assert False, f"{path} contains {match.group()!r}"


def test_an_unopened_seal_is_never_disclosed(ledgers, tmp_path):
    """The whole site must not leak the payload of a sealed-but-unopened commitment."""
    out = build_site(ledgers, tmp_path)
    for path in out.rglob("*.html"):
        assert "objective c-1" not in path.read_text(encoding="utf-8"), path
    # ...and there is no page for it either.
    assert not (out / "a/helios-3/c/c-1.html").exists()


def test_the_open_board_lists_nothing_that_is_already_resolved(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    board = read(out, "open.html")
    assert "c-0" not in board  # resolved, so not awaiting judgement


def test_the_open_board_excludes_broken_ledgers_and_says_so(ledgers, tmp_path):
    """selene-1's chain has a hole; nothing read from it belongs on a forward-looking
    page, and the reader is told a ledger was left out rather than silently dropped."""
    out = build_site(ledgers, tmp_path)
    board = read(out, "open.html")
    assert "s-0" not in board
    assert "s-2" not in board
    assert "chain is broken" in board
    assert "1 ledger is left out" in board


def test_the_registry_publishes_no_counts_for_a_broken_ledger(ledgers, tmp_path):
    """Same rule as the credential page: no figures beside a warning."""
    out = build_site(ledgers, tmp_path)
    page = read(out, "index.html")
    rows = {}
    for row in re.findall(r"<tr>(?:(?!</tr>).)*</tr>", page, re.S):
        for agent in ("helios-3", "selene-1"):
            if f">{agent}</a>" in row:
                rows[agent] = row

    assert "Record broken" in rows["selene-1"]
    assert not re.search(r">\s*\d+\s*<", rows["selene-1"]), rows["selene-1"]
    assert "Record intact" in rows["helios-3"]
    assert re.search(r">\s*\d+\s*<", rows["helios-3"]), rows["helios-3"]


def test_stub_pages_are_marked_and_carry_no_unlabelled_figures(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    for rel in ("launch.html", "feed.html", "standings.html"):
        page = read(out, rel)
        assert "Not built" in page, rel
        assert "Blocked on:" in page, rel
        assert "chip-sample" in page or "status-ok" in page, rel


def test_the_commitment_page_states_whether_it_was_sealed_first(ledgers, tmp_path):
    out = build_site(ledgers, tmp_path)
    sealed_first = read(out, "a/helios-3/c/c-0.html")
    assert "sealed before it was readable" in sealed_first
    written_clear = read(out, "a/selene-1/c/s-0.html")
    assert "written in the clear" in written_clear


def test_agent_names_and_ids_are_escaped_into_the_markup(tmp_path):
    d = tmp_path / "ledgers"
    d.mkdir()
    hostile = '<script>alert(1)</script>'
    ledger = Ledger(JsonlSink(d / "x.jsonl"), agent=hostile)
    ledger.commit(Commitment(
        agent=hostile, objective="<img onerror=x>", obligation=Obligation(
            statement="s", evidence_class="A", evidence_source="tx"),
        obligation_criteria="oc", outcome_criteria="uc",
        horizon="2026-09-01T00:00:00Z", sources=["s"], commitment_id="c-0",
    ))
    out = tmp_path / "site"
    build(str(d), str(out))
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in text, path
        assert "<img onerror=x>" not in text, path


def test_slug_refuses_to_escape_the_output_tree():
    assert _slug("helios-3") == "helios-3"
    assert "/" not in _slug("../../etc/passwd")
    assert ".." not in _slug("../../etc/passwd")
    for bad in ("..", ".", "", "///"):
        with pytest.raises(ValueError):
            _slug(bad)


def test_building_from_a_missing_directory_is_refused(tmp_path):
    with pytest.raises(ValueError, match="directory"):
        build(str(tmp_path / "nope"), str(tmp_path / "site"))


def test_an_empty_ledger_directory_still_produces_a_usable_site(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    out = tmp_path / "site"
    build(str(d), str(out))
    assert "0 agents on the record" in read(out, "index.html")
    assert (out / "verify.html").exists()
