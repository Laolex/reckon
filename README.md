# Reckon

**The capture layer for autonomous decisions.** Capture is the primitive; replay exists to
prove capture worked.

An autonomous system that made a decision you now regret leaves behind a record. The
question you want to ask that record is not "what happened" — it is *"would this have gone
the other way under a different policy?"* Reckon exists because that question is usually
unanswerable, and because nothing in the record tells you it is unanswerable.

## The one shot

Real OPA v1.18.2 probe output, both columns computed from the same evidence:

```
──────────────────────────────────────────────────────────────────────────
  OPA v1.18.2 — two decisions, one input, and what each record can support
──────────────────────────────────────────────────────────────────────────
                          AS OPA RECORDED IT          WITH RECKON

  input                   raw_edge=0.002              raw_edge=0.002
  bundle revision         policy-v2-code-only         policy-v2-code-only
  engine version          identical                   identical
  outcome                 trade / skip  ← opposite    admit / reject  ← opposite
  threshold in force      not in the record           0.0015 / 0.0025
  where it came from      not in the record           bundled / runtime_override
  runs distinguishable?   no — byte-identical         yes — 46e106a3aa9b… vs 7c6466eea414…

  verifier's answer       REFUSED — no class          C2 (Loosening Replay)
──────────────────────────────────────────────────────────────────────────
```

```bash
python -m demo.frame
```

The left column is a complete, correct decision log from a sound engine. The frame
raises `SystemExit` rather than printing if the verifier ever stops answering `none`
on the left or `C2` on the right, so it cannot show a result it did not get.

## The finding

Five systems were probed: OPA, LangGraph, Temporal, and the decision logs of a live
Hyperliquid and a live Polymarket agent. Every one produced records that looked sufficient
and were not.

Three are reproducible here from the original probe artifacts, in [`demo/`](demo/):

- **OPA.** A sound policy engine, versioned bundles and a complete decision log still
  produced two decisions with **identical input, identical bundle revision and identical
  engine version that came out opposite ways** — and nothing in the record revealed which
  regime was in force.
- **LangGraph.** Three threads, one identical persisted rationale, two different outcomes.
  The threshold that separated them occurs in **zero of 12,286 persisted bytes**. The record
  faithfully kept the reasoning that did not decide, and dropped the predicate that did.
- **Temporal.** The hardest case, since deterministic replay *is* its product. The same
  divergence — history says `trade`, replayed code decides `skip` — is caught when the
  decision schedules an activity and **silent when it only changes a returned value**.
  Detection is drawn at command boundaries, not at decisions.

So: replay soundness is not compositional. It is a property of the whole execution path, not
of the components in it. And no record carries its own soundness proof.

The argument in full is in [`docs/ARGUMENT.md`](docs/ARGUMENT.md), including the
non-goals and what would falsify it.

## Capability classes

The verifier reports a class, never a score. A percentage over incommensurable kinds of
missing evidence manufactures exactly the false confidence that made the OPA failure
undetectable.

| Class | Counterfactual | Additionally requires |
|---|---|---|
| **C0** Identity | reproduce what happened | execution model, determinism |
| **C1** Tightening | admit strictly fewer actions | predicate structure, compared value, resolved policy |
| **C2** Loosening | admit more actions | the rejected candidate set and their values |
| **C3** State-Coupled | a changed decision perturbs later state | **not certifiable by anyone** |

C0–C2 are deductive given capture. C3 is not deductive for anyone — past the first flip it
is counterfactual inference, not replay. Reckon's honest top guarantee is: certify soundness
through C2, and for C3 certify *where the evidence ends*.

## Install

```
pip install reckon-rcdr
```

Python 3.11+, no runtime dependencies. The distribution is `reckon-rcdr`; the import name
and the CLI command are both `reckon`.

## Use

```python
from reckon import JsonlSink, Recorder

rec = Recorder(sink=JsonlSink("run.jsonl"), run_id="run-1", emitter="my-agent")

with rec.decision(action="transfer", pure=True) as d:
    d.policy("policy.limit", value=5000, provenance="bundled", source="opa:bundle")
    allowed = d.check("lt", left="request.amount", value=4200, right="policy.limit")
    d.candidate("transfer", compared_value=4200, outcome="admit", predicate="p:limit")
    d.candidate("hold", compared_value=4200, outcome="reject", predicate="p:limit")
    d.candidates_exhaustive()
    d.admit() if allowed else d.reject()
```

```
$ python -m reckon verify run.jsonl --class C2
Requested: Loosening Replay (C2)
Available: C2
Decisions: C2 x1

$ python -m reckon boundary run.jsonl --decision d-4f21a0c9e113
```

Exit code is non-zero when the requested class is unsupported, so it can gate a pipeline. A
build should be able to fail because the evidence needed to re-adjudicate a decision was
never captured.

## The emitter refuses to guess

Comparing against a policy that was never registered raises. Closing a decision without an
outcome raises. `pure` is a declaration the caller makes, never something the SDK infers, so
an undeclared decision without a seed fails C0. Absent candidate completeness reads as
`taken_only`; unestablished provenance is written as `unknown` and caps the record at C0.

Each of those is deliberately inconvenient. A record that quietly fills its own gaps is the
failure this whole project is named after.

## Layout

| Path | |
|---|---|
| `docs/RCDR-v0.1.md` | the record format — the normative document |
| `docs/ARGUMENT.md` | the argument: thesis, evidence, novelty, non-goals |
| `src/reckon/` | emitter, verifier, run-level verifier, CLI |
| `demo/` | three before/after arcs over real probe artifacts, plus the ablation |
| `demo/ABLATION.md` | which fields are load-bearing — generated, not asserted |
| `tests/` | every assertion traces to a requirement in the spec |

```
pip install -e ".[dev]"
python -m pytest
```

## License

Apache-2.0. Chosen over MIT for the express patent grant: RCDR is meant to be implemented
by other people, and an implementer should not have to wonder about that.

## Scope

No tamper evidence, no signatures, no anchoring — the demonstrated threat is omission, not
modification. No confidentiality. No inference over uninstrumented systems: RCDR describes
what an instrumented emitter must produce, and recovering decision semantics from arbitrary
code is a separate and much harder problem. Any implementation reporting a C3 certification
is non-conforming.
