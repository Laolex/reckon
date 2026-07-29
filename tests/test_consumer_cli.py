import json

from reckon.__main__ import main


def seal_one(tmp_path, cid="c-1"):
    path = str(tmp_path / "helios-3.jsonl")
    code = main([
        "commit", "--ledger", path, "--agent", "helios-3",
        "--id", cid,
        "--objective", "increase treasury yield",
        "--obligation", "submit 10 qualifying applications",
        "--evidence-class", "B",
        "--evidence-source", "portal confirmations",
        "--obligation-criteria", "10 or more confirmed",
        "--outcome-criteria", "at least one award",
        "--horizon", "2026-09-01T00:00:00Z",
        "--source", "grants.example.org",
    ])
    return path, code


def test_commit_writes_one_sealed_record(tmp_path):
    path, code = seal_one(tmp_path)
    assert code == 0
    lines = [json.loads(l) for l in open(path)]
    assert len(lines) == 1
    assert lines[0]["seq"] == 0
    assert lines[0]["seal"].startswith("sha256:")


def test_second_invocation_resumes_the_chain(tmp_path):
    path, _ = seal_one(tmp_path, "c-1")
    seal_one(tmp_path, "c-2")
    lines = [json.loads(l) for l in open(path)]
    assert [l["seq"] for l in lines] == [0, 1]
    assert lines[1]["prev_hash"] != "sha256:genesis"


def test_resolve_appends_a_resolution(tmp_path):
    path, _ = seal_one(tmp_path)
    code = main([
        "resolve", "--ledger", path, "--agent", "helios-3",
        "--id", "c-1", "--obligation", "met", "--outcome", "missed",
        "--evidence", "portal=12 confirmations",
    ])
    assert code == 0
    last = [json.loads(l) for l in open(path)][-1]
    assert last["cell"] == "competent_unsuccessful"


def test_decline_appends_a_decline(tmp_path):
    path, _ = seal_one(tmp_path)
    assert main([
        "decline", "--ledger", path, "--agent", "helios-3",
        "--reason", "nothing qualified this week",
    ]) == 0
    last = [json.loads(l) for l in open(path)][-1]
    assert last["kind"] == "decline"
    assert last["seq"] == 1


def test_credential_exits_nonzero_when_the_chain_is_broken(tmp_path, capsys):
    path, _ = seal_one(tmp_path)
    with open(path, "a") as fh:
        fh.write(json.dumps({"kind": "decline", "agent": "helios-3", "seq": 5,
                             "prev_hash": "sha256:wrong", "reason": "x"}) + "\n")
    capsys.readouterr()  # drop the "sealed c-1" line from the seal above
    code = main(["credential", "--ledger", path, "--json"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["integrity"]["intact"] is False


def test_serve_is_registered_and_takes_a_port(tmp_path, monkeypatch):
    called = {}

    def fake_serve(ledger_path, port=8799):
        called["path"] = ledger_path
        called["port"] = port

    monkeypatch.setattr("reckon.page.serve", fake_serve)
    path, _ = seal_one(tmp_path)
    assert main(["serve", "--ledger", path, "--port", "8123"]) == 0
    assert called == {"path": path, "port": 8123}


def test_the_original_verify_command_still_works(tmp_path, capsys):
    """The consumer subcommands must not disturb the existing verifier CLI."""
    run = tmp_path / "run.jsonl"
    run.write_text("", encoding="utf-8")
    code = main(["verify", str(run), "--class", "C0", "--json"])
    capsys.readouterr()
    assert code in (0, 1)
