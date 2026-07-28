# Changelog

## 0.1.0 — 2026-07-28

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
