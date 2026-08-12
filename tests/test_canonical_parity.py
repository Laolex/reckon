"""Cross-language parity: the browser verifier must agree with the Python one.

A verifier that disagrees with the writer is worse than no verifier — it would call
honest records broken. The two implementations canonicalise independently, so this
runs the real `verify.js` under node and compares it against `reckon` on the same
inputs, byte for byte on the canonical form and hash for hash on the digest.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reckon.commitment import Commitment, Obligation
from reckon.integrity import verify_ledger
from reckon.ledger import Ledger
from reckon.record import digest
from reckon.resolve import Resolution
from reckon.sink import MemorySink

VERIFY_JS = Path(__file__).resolve().parents[1] / "src" / "reckon" / "assets" / "verify.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is needed to run the browser verifier"
)

# Values chosen for where the two languages disagree by default: non-ASCII (Python
# escapes, JS does not), an em dash we actually use in our own copy, unsorted keys,
# nesting, and the JSON scalars.
TRICKY = [
    "plain",
    "café",
    "naïve — dash",
    "—",
    "a\"b",
    "x\ny\tz",
    "àéîõü",
    "emoji \U0001f9fe receipt",
    {"b": 1, "a": 2, "é": 3, "A": 4},
    {"nested": {"z": ["—", 1, True, None], "a": {}}},
    [],
    {},
    0,
    -17,
    True,
    False,
    None,
    ["é", 1, True, None],
]


def run_node(script: str, payload) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed:\n{result.stderr}")
    return json.loads(result.stdout)


NODE_CANONICAL = f"""
const R = require({str(VERIFY_JS)!r});
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", async () => {{
  const values = JSON.parse(input);
  const out = [];
  for (const v of values) {{
    out.push({{ canonical: R.canonical(v), digest: await R.digest(v) }});
  }}
  process.stdout.write(JSON.stringify(out));
}});
"""

NODE_VERIFY = f"""
const R = require({str(VERIFY_JS)!r});
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", async () => {{
  const ledgers = JSON.parse(input);
  const out = [];
  for (const records of ledgers) {{
    out.push(await R.verifyLedger(records));
  }}
  process.stdout.write(JSON.stringify(out));
}});
"""


def python_canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def test_canonical_form_is_byte_identical():
    got = run_node(NODE_CANONICAL, TRICKY)
    for value, js in zip(TRICKY, got):
        assert js["canonical"] == python_canonical(value), value


def test_digests_agree():
    got = run_node(NODE_CANONICAL, TRICKY)
    for value, js in zip(TRICKY, got):
        assert js["digest"] == digest(value), value


def a_commitment(cid, cls="B", objective="increase treasury yield"):
    return Commitment(
        agent="helios-3",
        objective=objective,
        obligation=Obligation(
            statement="submit 10 qualifying applications",
            evidence_class=cls,
            evidence_source="portal confirmations",
        ),
        obligation_criteria="10 or more confirmed",
        outcome_criteria="at least one award",
        horizon="2026-09-01T00:00:00Z",
        # Deliberately out of order, and non-ASCII, so that dropping either the sort
        # or the escaping on the JS side changes the seal and fails this suite.
        sources=["é.example.org", "grants.example.org", "Alpha.example.org"],
        commitment_id=cid,
    )


def a_ledger():
    sink = MemorySink()
    ledger = Ledger(sink, agent="helios-3")
    # An objective with an em dash and an accent, because that is where parity breaks.
    ledger.commit(a_commitment("c-0", "A", "reduce spend — naïvely"))
    ledger.seal_only(a_commitment("c-1"))
    ledger.seal_only(a_commitment("c-2", "D"))
    ledger.decline(reason="nothing qualified — week 31")
    ledger.reveal(a_commitment("c-1"))
    ledger.append(Resolution("c-0", "met", "missed", {"tx": "0xabc"}).to_dict())
    ledger.append(Resolution("c-1", "missed", "met", {"note": "market moved"}).to_dict())
    return sink.records


def variants():
    """An intact ledger and one of each failure the verifier is meant to name."""
    intact = a_ledger()

    with_gap = a_ledger()
    del with_gap[3]

    edited = a_ledger()
    edited[0]["outcome_criteria"] = "tampered"

    forged_reveal = a_ledger()
    forged_reveal[4]["obligation"]["statement"] = "submit 3 applications"

    # Stored records always arrive with `sources` sorted, because the writer sorts
    # before sealing. A hand-written record need not, and both verifiers re-sort
    # before rehashing — so reordering sources must NOT break the seal, in either
    # language. This is the only case that exercises the JS-side sort at all.
    reordered = a_ledger()
    reordered[0]["sources"] = list(reversed(reordered[0]["sources"]))

    return {
        "intact": intact,
        "gap": with_gap,
        "edited_seal": edited,
        "forged_reveal": forged_reveal,
        "reordered_sources": reordered,
    }


def test_the_browser_verifier_reaches_the_same_verdict_on_every_variant():
    cases = variants()
    names = list(cases)
    js_reports = run_node(NODE_VERIFY, [cases[n] for n in names])

    for name, js in zip(names, js_reports):
        py = verify_ledger(cases[name]).to_dict()
        assert js["intact"] == py["intact"], name
        assert js["gaps"] == py["gaps"], name
        assert js["forks"] == py["forks"], name
        assert js["broken_seals"] == py["broken_seals"], name
        assert js["unmatched_reveals"] == py["unmatched_reveals"], name


def test_the_intact_case_really_is_intact_so_the_comparison_means_something():
    """Guards against both implementations agreeing that everything is broken."""
    assert verify_ledger(variants()["intact"]).intact
    for name in ("gap", "edited_seal", "forged_reveal"):
        assert not verify_ledger(variants()[name]).intact, name


def test_reordering_sources_does_not_break_a_seal_in_either_language():
    records = variants()["reordered_sources"]
    py = verify_ledger(records)
    assert py.broken_seals == []  # the writer sorted; the verifier sorts again
    js = run_node(NODE_VERIFY, [records])[0]
    assert js["broken_seals"] == []
