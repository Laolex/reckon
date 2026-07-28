"""The second before/after arc, over a real LangGraph checkpoint database.

The OPA arc shows a record that could not say *where* its policy came from. This one
shows something worse and more common: a record that faithfully preserved the model's
reasoning and dropped the value that actually decided.

`demo/evidence/langgraph-checkpoints.sqlite` is the checkpointer output of the probe in
`demo/evidence/langgraph_agent.py`, run on 2026-07-16 under three thread ids with
different values of `LG_MIN_EDGE_THRESHOLD`. All three produced the identical persisted
rationale. Two skipped and one traded.

The threshold that separated them appears in **zero bytes** of the database. So does the
compared value it was tested against. What survives is the sentence the model wrote, which
is the one part of the decision that did not decide anything.

Run with:  python -m demo.langgraph_replay      (from the repository root)
"""

import re
import sqlite3
from pathlib import Path

from reckon import MemorySink, Recorder, verify_run

EVIDENCE = Path(__file__).parent / "evidence" / "langgraph-checkpoints.sqlite"

# What was in force for each thread. Recovered from the probe's invocation, not from the
# database — because it is not in the database. That is the finding.
THRESHOLD_IN_FORCE = {"t1": 0.0025, "t2": 0.0015, "t3": 0.0025}

# The analyst marks fair value 20bp above market, so every thread compared the same number.
NET_EDGE = 0.002

RATIONALE = re.compile(rb"([A-Z]{2,5} mispriced vs 4h mean; fair value [0-9.]+)")


def persisted_bytes() -> dict[str, bytes]:
    """Everything the checkpointer wrote, per thread."""
    db = sqlite3.connect(EVIDENCE)
    per_thread: dict[str, bytes] = {}
    queries = (
        "select thread_id, checkpoint, metadata from checkpoints",
        "select thread_id, value, value from writes",
    )
    for query in queries:
        for thread_id, first, second in db.execute(query):
            for blob in (first, second):
                if blob:
                    per_thread[thread_id] = per_thread.get(thread_id, b"") + bytes(blob)
    db.close()
    return per_thread


def observed() -> dict[str, dict]:
    facts = {}
    for thread_id, blob in sorted(persisted_bytes().items()):
        actions = sorted({match.decode() for match in re.findall(rb"skip|trade", blob)})
        rationale = RATIONALE.search(blob)
        facts[thread_id] = {
            "action": actions[0] if len(actions) == 1 else "|".join(actions),
            "rationale": rationale.group(1).decode() if rationale else None,
            "bytes": len(blob),
        }
    return facts


def absent_terms() -> dict[str, int]:
    """Count the decisive terms across every byte the checkpointer persisted."""
    everything = b"".join(persisted_bytes().values())
    terms = [b"LG_MIN_EDGE_THRESHOLD", b"0.0025", b"0.0015", b"threshold", b"net_edge"]
    return {term.decode(): everything.count(term) for term in terms}


def as_rcdr(thread_id: str, facts: dict, sequence: int) -> dict:
    """Map a LangGraph thread into RCDR, claiming nothing the checkpoint recorded.

    There is no predicate structure to hash, no compared value, and no resolved policy —
    the gate ran in Python against an environment variable, and the checkpointer persists
    channel state rather than the comparisons that produced it. Provenance is `unknown`
    because the record cannot distinguish a threshold read from the environment from one
    that was hard-coded.
    """
    return {
        "rcdr_version": "0.1",
        "decision_id": thread_id,
        "run_id": "langgraph-probe",
        "sequence": sequence,
        "outcome": "admit" if facts["action"] == "trade" else "reject",
        "action": {"id": facts["action"]},
        "policy": {
            "key": "LG_MIN_EDGE_THRESHOLD",
            "resolution": {"provenance": "unknown", "source": "not persisted"},
        },
        "candidates": {"completeness": "taken_only", "items": []},
        "execution": {"runtime": "python3 + langgraph"},
        "capture": {"sdk_version": "n/a", "emitter": "langgraph-checkpoint-sqlite"},
    }


def before() -> None:
    facts = observed()
    print("BEFORE — LangGraph checkpoint database, mapped into RCDR\n")
    for thread_id, fact in facts.items():
        print(f"  {thread_id}  -> {fact['action']:5}  rationale: {fact['rationale']}")

    rationales = {fact["rationale"] for fact in facts.values()}
    actions = {fact["action"] for fact in facts.values()}
    print(
        f"\n  {len(rationales)} distinct rationale across {len(actions)} distinct outcomes."
    )
    print("  The record kept the reasoning that did not decide.\n")

    print("  Occurrences across every persisted byte:")
    for term, count in absent_terms().items():
        print(f"    {term:24} {count}")
    total = sum(len(blob) for blob in persisted_bytes().values())
    print(f"\n  {total} bytes persisted. The value that decided is in none of them.\n")

    records = [as_rcdr(tid, fact, i) for i, (tid, fact) in enumerate(facts.items())]
    print(verify_run(records, requested="C1").render())


def after() -> list[dict]:
    sink = MemorySink()
    rec = Recorder(sink=sink, run_id="langgraph-reemitted", emitter="langgraph-shim")

    for thread_id, threshold in THRESHOLD_IN_FORCE.items():
        with rec.decision(action="trade", pure=True) as d:
            # `environment` is a first-class provenance. An env-var threshold is not a
            # defect to hide; it is a fact the record has to be able to state.
            d.policy(
                "LG_MIN_EDGE_THRESHOLD",
                value=threshold,
                provenance="environment",
                source=f"env:{thread_id}",
            )
            passed = d.check(
                "gte", left="abs(net_edge)", value=NET_EDGE, right="LG_MIN_EDGE_THRESHOLD"
            )
            d.candidate(
                "trade",
                compared_value=NET_EDGE,
                outcome="admit" if passed else "reject",
                predicate="p:edge-gate",
            )
            d.candidate("skip", compared_value=NET_EDGE, outcome="reject", predicate="p:edge-gate")
            d.candidates_exhaustive()
            d.admit() if passed else d.reject()

    records = sink.records
    print("\n\nAFTER — the same three threads, emitted through Reckon\n")
    for thread_id, record in zip(THRESHOLD_IN_FORCE, records):
        print(
            f"  {thread_id}  compared={record['compared']['value']}  "
            f"vs resolved={record['policy']['resolved_value']}  "
            f"({record['policy']['resolution']['provenance']})  -> {record['outcome']}"
        )
    print("\n  The compared value and the value it was compared against are both present.")
    print("  Two threads are now distinguishable by more than their outcome.\n")
    print(verify_run(records, requested="C2").render())
    return records


def main() -> None:
    before()
    after()


if __name__ == "__main__":
    main()
