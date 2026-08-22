"""The verifier CLI. This is the surface a user actually meets."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "reckon", *args],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )


def write_run(tmp_path, exhaustive=True):
    sys.path.insert(0, str(ROOT / "src"))
    from reckon import JsonlSink, Recorder

    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "run.jsonl"
    rec = Recorder(sink=JsonlSink(path), run_id="r-1", emitter="test")
    with rec.decision(action="transfer", pure=True) as d:
        d.policy("policy.limit", value=100, provenance="bundled", source="opa:bundle")
        if exhaustive:
            d.candidate("transfer", compared_value=50, outcome="admit", predicate="p:b")
            d.candidates_exhaustive()
        d.check("lt", left="size", value=50, right="policy.limit")
        d.admit()
    return path


def test_cli_exits_zero_when_the_class_is_supported(tmp_path):
    result = run_cli("verify", str(write_run(tmp_path)), "--class", "C2")
    assert result.returncode == 0
    assert "Available: C2" in result.stdout


def test_cli_exits_nonzero_when_evidence_is_missing(tmp_path):
    """Non-zero so it can gate a pipeline, which is the point of instrumenting."""
    result = run_cli("verify", str(write_run(tmp_path, exhaustive=False)), "--class", "C2")
    assert result.returncode == 1
    assert "candidates.completeness = exhaustive" in result.stdout


def test_cli_emits_machine_readable_json(tmp_path):
    result = run_cli("verify", str(write_run(tmp_path)), "--class", "C2", "--json")
    payload = json.loads(result.stdout)
    assert payload["available"] == "C2"
    assert payload["satisfied"] is True
    assert payload["requested"] == "C2"
    assert "score" not in payload


def test_cli_refuses_to_certify_c3(tmp_path):
    result = run_cli("verify", str(write_run(tmp_path)), "--class", "C3")
    assert result.returncode == 1
    assert "not certifiable" in result.stdout


def test_cli_reports_the_boundary_for_a_decision(tmp_path):
    path = write_run(tmp_path)
    decision_id = json.loads(path.read_text().splitlines()[0])["decision_id"]
    result = run_cli("boundary", str(path), "--decision", decision_id)
    assert result.returncode == 0
    assert "Hypothesis" in result.stdout


def test_cli_compares_two_runs_and_writes_proof_screen(tmp_path):
    left = write_run(tmp_path / "left")
    right = write_run(tmp_path / "right")
    record = json.loads(right.read_text().splitlines()[0])
    record["compared"]["value"] = 200
    record["outcome"] = "reject"
    right.write_text(json.dumps(record) + "\n")
    proof = tmp_path / "proof" / "index.html"

    result = run_cli(
        "compare",
        str(left),
        str(right),
        "--guarantee",
        "transfer remains under limit",
        "--html-out",
        str(proof),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["first_evidence_divergence"] == "compared.value"
    assert "canonical RCDR records" in proof.read_text()
