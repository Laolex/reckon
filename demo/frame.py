"""The one shot that explains Reckon.

`demo/opa_replay.py` makes the full argument in about sixty lines of output.
This prints the same evidence as a single picture, because a reader who gives
this project three seconds should still leave with the finding:

    two decisions, identical input, identical bundle revision, opposite
    outcomes — and nothing in the record that says why.

The evidence is the real probe log from OPA v1.18.2 (2026-07-16), not a
fixture written to make this frame come out well. The frame refuses to print
at all unless the verifier still answers "none" for the as-recorded pair and
"C2" for the re-emitted one, so it cannot show a result it did not get.

Run with:  python -m demo.frame      (from the repository root)
"""

import contextlib
import io

from reckon import verify_run

from demo.opa_replay import after, as_rcdr, load_opa_decisions

PAD = 24


def render(title: str, rows: list[tuple[str, str, str]], footer: list[str]) -> str:
    width = max(len(row[1]) for row in rows)
    line = "─" * (PAD + width + 26)
    out = [
        line,
        f"  {title}",
        line,
        f"  {'':{PAD}}{'AS OPA RECORDED IT':{width + 4}}WITH RECKON",
        "",
    ]
    out += [f"  {label:{PAD}}{left:{width + 4}}{right}".rstrip() for label, left, right in rows]
    out += [line]
    out += [f"  {note}" for note in footer]
    return "\n".join(out)


def main() -> None:
    entries = load_opa_decisions()
    as_recorded = [as_rcdr(entry, index) for index, entry in enumerate(entries)]

    # The re-emitted pair, without opa_replay's own narration.
    with contextlib.redirect_stdout(io.StringIO()):
        reemitted = after()

    before_report = verify_run(as_recorded, requested="C1")
    after_report = verify_run(reemitted, requested="C2")

    if before_report.available is not None or after_report.available != "C2":
        raise SystemExit(
            "The frame did not hold: verifier answered "
            f"{before_report.available} / {after_report.available}. "
            "Refusing to print a picture that is not true."
        )

    digests = [record["execution"]["path_digest"][7:19] for record in reemitted]
    outcomes = [entry["result"]["action"] for entry in entries]

    print(
        render(
            "OPA v1.18.2 — two decisions, one input, and what each record can support",
            [
                ("input", "raw_edge=0.002", "raw_edge=0.002"),
                ("bundle revision", "policy-v2-code-only", "policy-v2-code-only"),
                ("engine version", "identical", "identical"),
                ("outcome", f"{outcomes[0]} / {outcomes[1]}  ← opposite", "admit / reject  ← opposite"),
                ("threshold in force", "not in the record", "0.0015 / 0.0025"),
                ("where it came from", "not in the record", "bundled / runtime_override"),
                ("runs distinguishable?", "no — byte-identical", f"yes — {digests[0]}… vs {digests[1]}…"),
                ("", "", ""),
                ("verifier's answer", "REFUSED — no class", "C2 (Loosening Replay)"),
            ],
            [
                "The left column is a complete, correct OPA decision log. The engine is",
                "sound, the bundles are versioned, nothing is broken — and the record",
                "still cannot tell the two runs apart, because a value was pushed through",
                "the Data API, outside the bundle's provenance boundary.",
                "",
                "No record carries its own soundness proof.",
            ],
        )
    )


if __name__ == "__main__":
    main()
