# Reckon — the argument

The case for the work, stated so it can be checked. The user documentation is in
[`README.md`](../README.md); the normative format is [`RCDR-v0.1.md`](RCDR-v0.1.md).

---

## The claim

> **No record carries its own soundness proof.**

Everything below is an attempt to make that concrete enough to be wrong.

## The thesis, stated narrowly

> In the systems we evaluated, replay soundness depends on information that is not
> self-contained in the execution record.

Stated narrowly on purpose. It is an empirical claim about five systems that were actually
probed, not a universal about all systems everywhere. The narrow version is harder to
refute and does not need to be walked back.

## The evidence

Five systems, all instrumented in good faith by competent people, all producing records
that looked sufficient and were not. The last of them, Temporal, is the one that should have
falsified the thesis.

| System | Highest class supported | Why it stops there |
|---|---|---|
| rr / Pernosco | C0 | records syscall results, not predicate structure |
| Hyperliquid agent log | < C1 | compared value never recorded; policy env-overridden |
| Polymarket signals log | cannot reach C2 | taken-only; rejected candidates absent |
| LangGraph checkpoint-sqlite | < C1 | threshold in zero persisted bytes; gates indistinct |
| OPA — config inside bundle roots | C1 | input plus resolved-via-bundle |
| OPA — config outside bundle roots | C1, **undetectable** | identical input and revision, opposite decisions |
| Temporal — decision crosses a command | C0, divergence **detected** | nondeterminism check fires |
| Temporal — decision does not | C0, divergence **silent** | detection is drawn at commands, not decisions |

Three of these are reproducible from this repository, with the original probe artifacts:

**OPA** (`python -m demo.opa_replay`) — two decisions, identical input, identical bundle
revision `policy-v2-code-only`, identical engine version 1.18.2, opposite outcomes. The
threshold had been pushed through the Data API, outside the bundle's declared roots. The
revision stayed accurate the whole time and stayed useless.

**LangGraph** (`python -m demo.langgraph_replay`) — three threads, one identical persisted
rationale, two distinct outcomes. The threshold that separated them occurs in **zero of
12,286 persisted bytes**, and so does the value it was compared against.

> The record faithfully kept the reasoning that did not decide, and dropped the predicate
> that did.

**Temporal** (`python -m demo.temporal_replay`) — the hardest case, because deterministic
replay *is* Temporal's product. The same decision was recorded under one threshold and
replayed under another, twice, differing only in whether the decision crossed a **command
boundary**:

| | history says | replayed code decided | Temporal reported |
|---|---|---|---|
| branch schedules an activity | trade | skip | `NondeterminismError` |
| branch only changes the value | trade | skip | **nothing — replay succeeded** |

Identical divergence. Detection in one case, silence in the other. What separates them is
not the decision or its importance — it is whether the decision happened to schedule an
activity. And the silent case is the one that matters: a decision that only changes a
returned value is an approval flag, a payout amount, a credit limit.

The history records `binaryChecksum` to identify the code that ran. The **same checksum
produced both decisions**, because the threshold is not in the build. A component identity
is not a path digest — the same failure as OPA's bundle revision, reached through an
entirely different mechanism, in a system built by different people for a different purpose.
That is what raises non-compositionality from an anecdote to a pattern.

None of these is a bug report. OPA's engine is sound, its bundles are versioned, its decision log
is complete by its own contract. Temporal honours its replay guarantee exactly as specified.
That is exactly what makes them the right examples: everything meant to make the decision
reproducible was in place, and the record still could not answer *"would this have gone the
other way under a different threshold?"*

Temporal also sharpens the claim in a way the other two could not. It is not that these
systems record too little by accident. Temporal draws its correctness boundary at commands
because commands are what durable execution must get right. The boundary is principled, and
it still lands in the wrong place for re-adjudicating a decision.

## What follows

**Replay soundness is not compositional.** A sound engine, versioned bundles and complete
logs still lost C1 because one deployment choice sat outside the recorded evidence. It is a
property of the whole execution path, not of the components in it. `execution.path_digest`
exists for this reason and for no other.

**Soundness is a relation, not a property.** `soundness = f(record, counterfactual class,
execution model)`. The same bytes are sound for one question and undefined for another, so a
verifier that returns a single score is answering a question nobody asked.

## The four classes, and the cliff

| Class | Counterfactual | Additionally requires |
|---|---|---|
| **C0** Identity | reproduce what happened | execution model, determinism |
| **C1** Tightening | admit strictly fewer actions | predicate structure, compared value, resolved policy |
| **C2** Loosening | admit more actions | the rejected candidate set and their values |
| **C3** State-Coupled | a changed decision perturbs later state | **not certifiable by anyone** |

C0–C2 are deductive given capture. C3 is not deductive for anyone: past the first flip you
are doing counterfactual inference, not replay. So the honest top guarantee is **certify
soundness through C2, and for C3 certify where the evidence ends** — which is what
`reckon boundary` does, splitting a run into an evidence region and a hypothesis region and
naming the edge between them.

This is the one result worth arguing with. It says a whole class of question that people
currently believe tooling will eventually answer is not a tooling problem at all.

## Novelty, against the obvious objection

**"This is rr."** rr and Pernosco moved the replay boundary far enough to reproduce an
execution, from the syscall interface. They replay the *same* run and claim nothing above
it — they cannot re-adjudicate a different policy, because a syscall result does not carry
the structure of the predicate that consumed it.

Reckon moves the boundary from execution to **decision semantics**. rr records what the
program received; Reckon records what the program compared, against what, resolved from
where. That difference is the product. "New invariant" would not be a defensible claim;
this is.

## Does every field earn its place?

[`demo/ABLATION.md`](../demo/ABLATION.md), generated by `python -m demo.ablation`: each
field is deleted from a C2-complete record and the verifier re-run. **10 of 13 fields are
load-bearing.** The three that are not — `ts`, `action.params_digest`, `capture.sdk_version`
— are named as decoration rather than defended, and a test fails if that set ever changes
silently.

Every load-bearing field exists because a real system omitted it and nothing in its record
revealed the omission.

## Non-goals, said out loud

These are limits, not oversights. A reader should hear them from us first.

- **Uninstrumented systems.** RCDR describes what an instrumented emitter must produce.
  Recovering decision semantics from arbitrary code needs per-language, per-framework static
  analysis — the hard half of a company. The demos' "before" mappings were written by hand,
  by someone who already knew the answer.
- **C3.** Never certified, by us or by anyone. Any implementation reporting a C3
  certification is non-conforming.
- **Tamper evidence, signatures, anchoring.** The demonstrated threat is omission, not
  modification. Adding cryptography would import a stack that solves none of the four
  capture failures found.
- **Confidentiality.** Records may hold sensitive values; that is the host's problem.
- **A standard.** A solo builder cannot will a format into existence by publishing it. The
  product is the SDK and the verifier. The spec is design discipline that happens to be
  publishable.

## What is actually built

Emitter, verifier, run-level verifier, C3 boundary reporter, CLI, three reproducible
before/after arcs, and a generated ablation. 56 tests, green on Python 3.11–3.13, with the
built wheel proven to install and run from a clean interpreter in CI.

The emitter refuses to guess: comparing against an unregistered policy raises, closing a
decision without an outcome raises, `pure` is a declaration rather than a detection,
unestablished provenance is written `unknown` and caps the record at C0, and an undeclared
candidate set reads `taken_only`. Each of those is deliberately inconvenient, because a
record that quietly fills its own gaps is the failure this project is named after.

## What would falsify this

- A widely-used decision record that already carries predicate structure, compared value and
  resolved policy with provenance. We did not find one; we looked at five, including the one
  system whose entire product is deterministic replay.
- A construction that certifies C3 soundly. That would be a better result than ours, and we
  would rather know.
- An ablation showing a load-bearing field is not. The table is generated, so it can be
  re-run against a counterexample.
