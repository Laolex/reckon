"""`python -m reckon` — the verifier CLI.

Exit code 1 when the requested class is not supported, so this can gate a pipeline.
That is the whole point of instrumenting: a build should be able to fail because the
evidence needed to re-adjudicate a decision was never captured.
"""

import argparse
import json
import sys
from pathlib import Path

from .commitment import EVIDENCE_CLASSES, Commitment, Obligation
from .credential import project
from .execution import SDK_VERSION
from .ledger import GENESIS_HASH, Ledger, read
from .record import digest
from .resolve import VERDICTS, Resolution
from .run import boundary, verify_run
from .sink import JsonlSink
from .verify import CLASS_NAMES


def load(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def open_ledger(path: str, agent: str) -> Ledger:
    """Resume sequence and chain from an existing file, or start at genesis.

    Without this every invocation would restart at sequence 0 and fork the chain,
    which is exactly the failure the chain exists to detect.
    """
    if Path(path).exists():
        records = read(path)
        if records:
            last = records[-1]
            return Ledger(JsonlSink(path), agent,
                          start_seq=last["seq"] + 1, prev_hash=digest(last))
    return Ledger(JsonlSink(path), agent, start_seq=0, prev_hash=GENESIS_HASH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reckon", description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version=f"reckon {SDK_VERSION} (RCDR v0.1)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify_cmd = sub.add_parser("verify", help="report the class a run supports")
    verify_cmd.add_argument("path", help="path to an RCDR .jsonl run")
    verify_cmd.add_argument(
        "--class",
        dest="requested",
        default="C1",
        choices=sorted(CLASS_NAMES),
        help="the counterfactual class you want to run",
    )
    verify_cmd.add_argument("--json", action="store_true", help="machine-readable output")

    boundary_cmd = sub.add_parser(
        "boundary", help="locate where evidence ends for a counterfactual"
    )
    boundary_cmd.add_argument("path")
    boundary_cmd.add_argument("--decision", required=True, help="the decision to flip")
    boundary_cmd.add_argument("--json", action="store_true")

    commit_cmd = sub.add_parser("commit", help="seal a commitment into a ledger")
    commit_cmd.add_argument("--ledger", required=True)
    commit_cmd.add_argument("--agent", required=True)
    commit_cmd.add_argument("--id", required=True, dest="cid")
    commit_cmd.add_argument("--objective", required=True)
    commit_cmd.add_argument("--obligation", required=True)
    commit_cmd.add_argument("--evidence-class", required=True, choices=EVIDENCE_CLASSES)
    commit_cmd.add_argument("--evidence-source", required=True)
    commit_cmd.add_argument("--obligation-criteria", required=True)
    commit_cmd.add_argument("--outcome-criteria", required=True)
    commit_cmd.add_argument("--horizon", required=True)
    commit_cmd.add_argument("--source", action="append", default=[], dest="sources")

    decline_cmd = sub.add_parser("decline", help="record that no commitment was made")
    decline_cmd.add_argument("--ledger", required=True)
    decline_cmd.add_argument("--agent", required=True)
    decline_cmd.add_argument("--reason", required=True)

    resolve_cmd = sub.add_parser("resolve", help="append a resolution")
    resolve_cmd.add_argument("--ledger", required=True)
    resolve_cmd.add_argument("--agent", required=True)
    resolve_cmd.add_argument("--id", required=True, dest="cid")
    resolve_cmd.add_argument("--obligation", required=True, choices=VERDICTS)
    resolve_cmd.add_argument("--outcome", required=True, choices=VERDICTS)
    resolve_cmd.add_argument("--evidence", action="append", required=True,
                             help="key=value, repeatable")

    cred_cmd = sub.add_parser("credential", help="project the credential from a ledger")
    cred_cmd.add_argument("--ledger", required=True)
    cred_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "commit":
        ledger = open_ledger(args.ledger, args.agent)
        ledger.commit(Commitment(
            agent=args.agent,
            objective=args.objective,
            obligation=Obligation(
                statement=args.obligation,
                evidence_class=args.evidence_class,
                evidence_source=args.evidence_source,
            ),
            obligation_criteria=args.obligation_criteria,
            outcome_criteria=args.outcome_criteria,
            horizon=args.horizon,
            sources=args.sources,
            commitment_id=args.cid,
        ))
        print(f"sealed {args.cid}")
        return 0

    if args.command == "decline":
        open_ledger(args.ledger, args.agent).decline(reason=args.reason)
        print("declined")
        return 0

    if args.command == "resolve":
        evidence = dict(item.split("=", 1) for item in args.evidence)
        ledger = open_ledger(args.ledger, args.agent)
        resolution = Resolution(args.cid, args.obligation, args.outcome, evidence)
        ledger.append(resolution.to_dict())
        print(f"{args.cid}: {resolution.cell()}")
        return 0

    if args.command == "credential":
        credential = project(read(args.ledger))
        if args.json:
            print(json.dumps(credential.to_dict(), indent=2))
        else:
            print(credential.integrity.render())
        return 0 if credential.integrity.intact else 1

    records = load(args.path)

    if args.command == "verify":
        report = verify_run(records, requested=args.requested)
        print(json.dumps(report.to_dict(), indent=2) if args.json else report.render())
        return 0 if report.satisfied else 1

    edge = boundary(records, args.decision)
    print(json.dumps(edge.to_dict(), indent=2) if args.json else edge.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
