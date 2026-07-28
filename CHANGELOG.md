# Changelog

## 0.1.1 — 2026-07-28

First published release. No API change from 0.1.0; the additions are evidence and
documentation, which for this project is the substance rather than the packaging.

### Evidence

- **Temporal probe** (`demo/temporal_replay.py`). The hardest case for the thesis, since
  deterministic replay is Temporal's product. The same decision recorded under one threshold
  and replayed under another diverges identically in both cases, but is caught only when it
  crosses a command boundary; when it merely changes a returned value, replay succeeds
  silently while the replayed code decides the opposite. The history's `binaryChecksum` is
  identical across both decisions, because the threshold is not in the build.
- **LangGraph probe** (`demo/langgraph_replay.py`). Three threads, one identical persisted
  rationale, two outcomes; the deciding threshold occurs in zero of 12,286 persisted bytes.
  The re-emitted records reproduce all three observed outcomes.
- **Ablation** (`demo/ablation.py` → `demo/ABLATION.md`). Each field deleted from a
  C2-complete record and the verifier re-run: 10 of 13 fields are load-bearing, and the three
  that are not are named rather than defended.

### Docs

- `docs/ARGUMENT.md` — the thesis stated narrowly, the evidence, the rr boundary, the
  non-goals, and what would falsify the whole thing.
- `docs/RCDR-v0.1.md` §3.1 separates **admissibility** from soundness: a class states what
  the evidence supports, not what a system may do with it. Demotion only; never gate on
  self-confidence; undeclared reversibility reads as irreversible.
- `execution.pure` documented in §4.8, which §5.1 already relied on.

## 0.1.0 — 2026-07-28 (unpublished)

First release. Implements RCDR v0.1 (`docs/RCDR-v0.1.md`) end to end.

### Emitter

- `Recorder` / `Decision` context manager emitting RCDR records to a sink.
- `predicate.id` is a content hash of canonical predicate structure — operator plus
  operand identities — rather than a name or source location.
- `policy.resolution.provenance` is a closed enum including `unknown`, which caps a
  record at C0. Invalid values raise rather than being coerced.
- `candidates.completeness` defaults to `taken_only`; `exhaustive` is an explicit
  declaration the caller makes and is never inferred from candidates having been logged.
- `execution.path_digest` covers the resolution sources actually used, so two decisions
  with identical dependencies but different resolution regimes hash differently.
- The emitter refuses to guess: comparing against an unregistered policy raises, and
  closing a decision without an outcome raises.
- `JsonlSink` and `MemorySink`.

### Verifier

- `verify()` implements §5.1 exactly and reports a capability class, never a score.
- `verify_run()` reports a run at its weakest decision and names which decisions fell
  short and what they were missing.
- `boundary()` reports the C3 boundary: given a decision to flip, it splits the run into
  an evidence region and a hypothesis region and names the edge where evidence ends.
  C3 is never certified.

### CLI

- `reckon verify <run.jsonl> --class C{0,1,2,3} [--json]`, exit code 1 when the requested
  class is unsupported so it can gate a pipeline.
- `reckon boundary <run.jsonl> --decision <id> [--json]`.

### Demo

- `demo/` runs the before/after arc over the decision log from a real OPA v1.18.2 probe
  containing two decisions with identical input, bundle revision and engine version that
  came out opposite ways.

### Known scope limits

No tamper evidence, no signatures, no anchoring — the demonstrated threat is omission.
No confidentiality. No inference over uninstrumented systems: the demo's "before" mapping
was written by hand. Any implementation reporting a C3 certification is non-conforming.
