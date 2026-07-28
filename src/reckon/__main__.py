"""`python -m reckon` — the verifier CLI.

Exit code 1 when the requested class is not supported, so this can gate a pipeline.
That is the whole point of instrumenting: a build should be able to fail because the
evidence needed to re-adjudicate a decision was never captured.
"""

import argparse
import json
import sys
from pathlib import Path

from .run import boundary, verify_run
from .verify import CLASS_NAMES


def load(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reckon", description=__doc__)
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

    args = parser.parse_args(argv)
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
