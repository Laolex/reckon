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
    capsys.readouterr()  # drop the commit confirmation printed above
    code = main(["credential", "--ledger", path, "--json"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["integrity"]["intact"] is False


def commitment_args(path, cid, *, statement="submit 10 qualifying applications"):
    return [
        "--ledger", path, "--agent", "helios-3", "--id", cid,
        "--objective", "increase treasury yield",
        "--obligation", statement,
        "--evidence-class", "B",
        "--evidence-source", "portal confirmations",
        "--obligation-criteria", "10 or more confirmed",
        "--outcome-criteria", "at least one award",
        "--horizon", "2026-09-01T00:00:00Z",
        "--source", "grants.example.org",
    ]


def test_seal_then_reveal_round_trips_through_the_cli(tmp_path):
    path = str(tmp_path / "helios-3.jsonl")
    assert main(["seal"] + commitment_args(path, "c-1")) == 0
    sealed = [json.loads(l) for l in open(path)][0]
    assert sealed["kind"] == "sealed_commitment"
    assert "objective" not in sealed  # the payload is not disclosed yet

    assert main(["reveal"] + commitment_args(path, "c-1")) == 0
    assert main(["credential", "--ledger", path, "--json"]) == 0


def test_an_unopened_seal_shows_up_on_the_credential(tmp_path, capsys):
    path = str(tmp_path / "helios-3.jsonl")
    main(["seal"] + commitment_args(path, "c-1"))
    main(["seal"] + commitment_args(path, "c-2"))
    main(["reveal"] + commitment_args(path, "c-1"))
    capsys.readouterr()
    assert main(["credential", "--ledger", path, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["unopened"] == 1


def test_revealing_a_payload_that_was_never_sealed_fails_the_credential(tmp_path, capsys):
    path = str(tmp_path / "helios-3.jsonl")
    main(["seal"] + commitment_args(path, "c-1"))
    main(["reveal"] + commitment_args(path, "c-1", statement="submit 3 applications"))
    capsys.readouterr()
    assert main(["credential", "--ledger", path, "--json"]) == 1
    report = json.loads(capsys.readouterr().out)["integrity"]
    assert report["unmatched_reveals"] == ["c-1"]


def test_the_original_verify_command_still_works(tmp_path, capsys):
    """The consumer subcommands must not disturb the existing verifier CLI."""
    run = tmp_path / "run.jsonl"
    run.write_text("", encoding="utf-8")
    code = main(["verify", str(run), "--class", "C0", "--json"])
    capsys.readouterr()
    assert code in (0, 1)


def test_build_site_writes_a_site_from_a_ledger_directory(tmp_path, capsys):
    ledgers = tmp_path / "ledgers"
    ledgers.mkdir()
    path = str(ledgers / "helios-3.jsonl")
    main(["commit"] + commitment_args(path, "c-1"))
    capsys.readouterr()
    out = tmp_path / "site"
    assert main(["build-site", "--ledgers", str(ledgers), "--out", str(out)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert (out / "index.html").exists()
    assert (out / "a/helios-3/index.html").exists()
