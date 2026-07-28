"""The third arc, over Temporal — the hardest case for the thesis.

Temporal is not an observability tool that forgot to record something. Deterministic
replay *is* its product: it replays workflow code against a recorded event history and
raises `NondeterminismError` when the code diverges from what the history says happened.
If any system's record were self-sufficient, it would be this one.

The probe (`evidence/temporal/probe.py`) runs the same decision twice, changing only
whether the decision crosses a **command boundary** — Temporal's unit of recorded action.

  A. GateWithCommand     a 'trade' schedules a second activity, so the branch is a command
  B. GateWithoutCommand  the branch only changes the returned value, so it is not

Each was recorded under threshold 0.0015 (decision: trade) and then replayed with the
threshold changed to 0.0025 underneath it. The results are in `evidence/temporal/findings.json`.

    A  ->  NondeterminismError. Temporal caught it.
    B  ->  Replay succeeded, no error. The replayed code decided `skip`
           while the history says `trade`.

**This is not a bug in Temporal.** Its guarantee is about replaying the same run under the
same code, and it honours that guarantee exactly. What the probe locates is the *boundary*
of the guarantee, and the boundary is drawn at commands rather than at decisions. So whether
a wrong decision is detected depends on whether that decision happens to schedule an
activity — an implementation detail with no relationship to how much the decision matters.

The dangerous case is the undetected one. A decision that only changes a returned value is
an approval flag, a payout amount, a risk score, a credit limit.

Run with:  python -m demo.temporal_replay      (from the repository root)
"""

import json
from pathlib import Path

from reckon import MemorySink, Recorder, verify_run

EVIDENCE = Path(__file__).parent / "evidence" / "temporal"

# Recorded under 0.0015 (trade); replayed under 0.0025 (skip). Neither value is in the history.
RECORDED_THRESHOLD = 0.0015
REPLAYED_THRESHOLD = 0.0025
NET_EDGE = 0.002

ABSENT_TERMS = ("0.0025", "0.0015", "MIN_EDGE_THRESHOLD", "threshold", "net_edge", "0.002")


def findings() -> dict:
    return json.loads((EVIDENCE / "findings.json").read_text())


def history(case: str) -> dict:
    return json.loads((EVIDENCE / f"history-{case.lower()}.json").read_text())


def component_identity(case: str) -> dict:
    """What the history records to identify the code that ran."""
    for event in history(case)["events"]:
        attrs = event.get("workflowTaskCompletedEventAttributes")
        if attrs and attrs.get("binaryChecksum"):
            return {
                "binaryChecksum": attrs["binaryChecksum"],
                "sdkVersion": attrs.get("sdkMetadata", {}).get("sdkVersion"),
            }
    return {}


def absent(case: str) -> dict[str, int]:
    raw = json.dumps(history(case))
    return {term: raw.count(term) for term in ABSENT_TERMS}


def as_rcdr(case: str, sequence: int) -> dict:
    """Map a Temporal history into RCDR.

    Temporal genuinely reproduces the run, so it is tempting to map this at C0. It is not
    mapped there, for the same reason OPA's bundle revision was not mapped to
    `path_digest`: `binaryChecksum` identifies the worker build, and the threshold is not
    in the build. In this probe the identical checksum produced both decisions.

    A component identity is not a path digest. That is the whole non-compositionality
    claim, and Temporal reproduces it through an entirely different mechanism than OPA did.
    """
    result = findings()[case]
    return {
        "rcdr_version": "0.1",
        "decision_id": f"temporal-{case.lower()}",
        "run_id": "temporal-probe",
        "sequence": sequence,
        "outcome": "admit" if result["result"]["action"] == "trade" else "reject",
        "action": {"id": result["result"]["action"]},
        "policy": {
            "key": "MIN_EDGE_THRESHOLD",
            "resolution": {"provenance": "unknown", "source": "worker config, not in history"},
        },
        "candidates": {"completeness": "taken_only", "items": []},
        "execution": {
            "runtime": "python3 + temporalio",
            # binaryChecksum is recorded, but it is a component version, not a path digest.
            "component_checksum": component_identity(case).get("binaryChecksum"),
        },
        "capture": {"sdk_version": "n/a", "emitter": "temporal-event-history"},
    }


def before() -> None:
    data = findings()
    print("BEFORE — Temporal event history\n")
    print("  Both cases recorded under threshold 0.0015, then replayed under 0.0025.\n")

    for case, label in (("A", "branch schedules an activity  (command boundary)"),
                        ("B", "branch only changes the value (no command boundary)")):
        result = data[case]
        detected = "NondeterminismError" in result["replay"]
        print(f"  {case}. {label}")
        print(f"       history says:            {result['result']['action']}")
        print(f"       replayed code decided:   {result['replay_decided']}")
        print(f"       Temporal reported:       {'CAUGHT IT' if detected else 'nothing — replay succeeded'}")
        print()

    print("  The same wrong decision is caught in one case and silent in the other.")
    print("  What differs is not the decision. It is whether it scheduled an activity.\n")

    print("  What the history records to identify the code:")
    for case in ("A", "B"):
        identity = component_identity(case)
        print(f"    {case}: binaryChecksum={identity.get('binaryChecksum')} sdk={identity.get('sdkVersion')}")
    print("    The same checksum produced both decisions. The threshold is not in the build.\n")

    print("  Occurrences in the event history:")
    for term, count in absent("B").items():
        print(f"    {term:22} {count}")
    print()

    records = [as_rcdr("A", 0), as_rcdr("B", 1)]
    print(verify_run(records, requested="C1").render())


def after() -> list[dict]:
    sink = MemorySink()
    rec = Recorder(sink=sink, run_id="temporal-reemitted", emitter="temporal-shim")

    for label, threshold in (("recorded", RECORDED_THRESHOLD), ("replayed", REPLAYED_THRESHOLD)):
        with rec.decision(action="trade", pure=True) as d:
            d.policy(
                "MIN_EDGE_THRESHOLD",
                value=threshold,
                provenance="computed",
                source=f"worker config @ {label}",
            )
            passed = d.check("gte", left="abs(net_edge)", value=NET_EDGE, right="MIN_EDGE_THRESHOLD")
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
    print("\n\nAFTER — the same two evaluations, emitted through Reckon\n")
    for record in records:
        print(
            f"  compared={record['compared']['value']} "
            f"vs resolved={record['policy']['resolved_value']} "
            f"-> {record['outcome']}   path={record['execution']['path_digest'][7:19]}…"
        )
    print("\n  The divergence Temporal could not see is now a difference in the record.")
    print("  No replay is required to detect it — the two records simply disagree.\n")
    print(verify_run(records, requested="C2").render())
    return records


def main() -> None:
    before()
    after()


if __name__ == "__main__":
    main()
