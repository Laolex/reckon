"""The before/after arc, run against a real OPA decision log.

`demo/evidence/opa-bundled2.log` is not a fixture written for this demo. It is the
output of a probe run against OPA v1.18.2 on 2026-07-16. It contains two decisions
with **identical input, identical bundle revision and identical engine version** that
came out opposite ways, because between them `min_edge_threshold` was pushed through
the Data API — outside the bundle's provenance boundary.

Nothing in OPA's record says that happened. That is the finding, and it is not a bug
in OPA: the engine is sound, the bundles are versioned, the decision log is complete.
The record still cannot carry the counterfactual, because replay soundness is a
property of the whole execution path and the record only described components of it.

    BEFORE — map the OPA log into RCDR as faithfully as it permits, and ask the
             verifier what class it supports.
    AFTER  — emit the same two decisions through the Reckon SDK and ask again.

Run with:  python -m demo.opa_replay      (from the repository root)
"""

import json
from pathlib import Path

from reckon import JsonlSink, MemorySink, Recorder, verify_run

EVIDENCE = Path(__file__).parent / "evidence" / "opa-bundled2.log"

# What was actually in force for each of the two decisions. Recovered by hand from
# the probe's setup — which is the point: it had to be recovered by hand, because the
# record did not carry it.
THRESHOLD_IN_FORCE = [0.0015, 0.0025]


def load_opa_decisions() -> list[dict]:
    records = []
    for line in EVIDENCE.read_text().splitlines():
        entry = json.loads(line)
        if entry.get("msg") == "Decision Log":
            records.append(entry)
    return records


def as_rcdr(entry: dict, sequence: int) -> dict:
    """Map an OPA decision-log entry into RCDR, claiming nothing OPA did not record.

    Two mappings are deliberately *not* made, and they are the whole demonstration:

    - The bundle revision is not mapped to `execution.path_digest`. A bundle revision
      is a component version. The path digest exists precisely because component
      versions do not distinguish these two runs — here they are byte-identical.
    - The bundle revision is not mapped to `policy.resolved_value` either. A pointer
      is not a value (§4.4), and in this log the pointer was accurate while the value
      it implied was wrong.

    Provenance is therefore `unknown`. That is not a defect of the mapping; it is the
    honest reading, and §4.4 caps such a record at C0 on purpose.
    """
    revision = entry.get("bundles", {}).get("authz", {}).get("revision")
    return {
        "rcdr_version": "0.1",
        "decision_id": entry["decision_id"],
        "run_id": entry["labels"]["id"],
        "sequence": sequence,
        "ts": entry["timestamp"],
        "outcome": "admit" if entry["result"]["action"] == "trade" else "reject",
        "action": {"id": entry["result"]["action"]},
        "policy": {
            "key": "data.config.min_edge_threshold",
            "resolution": {"provenance": "unknown", "source": "opa:bundle", "revision": revision},
        },
        "candidates": {"completeness": "taken_only", "items": []},
        "execution": {"runtime": f"opa{entry['labels']['version']}"},
        "capture": {"sdk_version": "n/a", "emitter": "opa-decision-log"},
    }


def before() -> None:
    entries = load_opa_decisions()
    records = [as_rcdr(entry, index) for index, entry in enumerate(entries)]

    print("BEFORE — OPA decision log, mapped into RCDR\n")
    for entry in entries:
        print(
            f"  {entry['decision_id'][:8]}  "
            f"raw_edge={entry['input']['raw_edge']}  "
            f"revision={entry['bundles']['authz']['revision']}  "
            f"-> {entry['result']['action']}"
        )
    print("\n  Same input. Same revision. Same engine version. Opposite decisions.\n")
    print(verify_run(records, requested="C1").render())


def after(out: Path | None = None) -> list[dict]:
    sink = JsonlSink(out) if out else MemorySink()
    rec = Recorder(sink=sink, run_id="opa-probe-reemitted", emitter="opa-shim")

    for threshold in THRESHOLD_IN_FORCE:
        with rec.decision(action="trade", pure=True) as d:
            d.policy(
                "data.config.min_edge_threshold",
                value=threshold,
                # The Data API push is expressible. That is the entire fix.
                provenance="runtime_override" if threshold != 0.0015 else "bundled",
                source="opa:data-api" if threshold != 0.0015 else "opa:bundle",
                revision="policy-v2-code-only",
            )
            passed = d.check(
                "gte", left="abs(net_edge)", value=0.0020, right="data.config.min_edge_threshold"
            )
            d.candidate(
                "trade",
                compared_value=0.0020,
                outcome="admit" if passed else "reject",
                predicate="p:gate-a",
            )
            d.candidate("skip", compared_value=0.0020, outcome="reject", predicate="p:gate-a")
            d.candidates_exhaustive()
            d.admit() if passed else d.reject()

    records = sink.records if isinstance(sink, MemorySink) else [
        json.loads(line) for line in Path(out).read_text().splitlines()
    ]

    print("\n\nAFTER — the same two decisions, emitted through Reckon\n")
    for record in records:
        print(
            f"  {record['decision_id']}  "
            f"resolved={record['policy']['resolved_value']}  "
            f"provenance={record['policy']['resolution']['provenance']}  "
            f"-> {record['outcome']}"
        )
    a, b = records[0]["execution"]["path_digest"], records[1]["execution"]["path_digest"]
    print(f"\n  path_digest differs: {a[7:19]}… vs {b[7:19]}…")
    print("  The two runs are now distinguishable in the record itself.\n")
    print(verify_run(records, requested="C2").render())
    return records


def main() -> None:
    before()
    after()


if __name__ == "__main__":
    main()
