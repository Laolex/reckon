# The OPA replay demo

```
python -m demo.opa_replay
```

## What the evidence is

`evidence/opa-bundled2.log` is the decision log from a probe run against OPA v1.18.2 on
2026-07-16, using the Rego policy in `evidence/policy.rego` — a transcription of a real
position-sizing gate. It contains two decisions:

| decision | input | bundle revision | engine | result |
|---|---|---|---|---|
| `ca4f88c4` | `raw_edge=0.002`, `equity=5000` | `policy-v2-code-only` | 1.18.2 | **trade** |
| `468228f8` | `raw_edge=0.002`, `equity=5000` | `policy-v2-code-only` | 1.18.2 | **skip** |

Identical input. Identical bundle revision. Identical engine version. Opposite decisions.

Between them, `min_edge_threshold` was pushed through OPA's Data API — outside the bundle's
provenance boundary. The bundle revision stayed accurate the whole time, and stayed useless,
because it described a component rather than the path.

**This is not a bug in OPA.** The engine is sound, the bundles are versioned, the decision
log is complete by its own contract. That is what makes it the right example: everything
that was supposed to make the decision reproducible was in place, and the record still could
not answer "would this have gone the other way under a different threshold?"

## Before

The demo maps that log into RCDR as faithfully as the log permits, then asks the verifier
for C1 — the class you need in order to re-adjudicate a decision under a *tighter* policy.

Two mappings are deliberately withheld, and they carry the argument:

- The bundle revision is **not** mapped to `execution.path_digest`. A revision is a
  component version; the path digest exists because component versions do not distinguish
  these two runs. Here they are byte-identical.
- The bundle revision is **not** mapped to `policy.resolved_value`. A pointer is not a value
  (§4.4) — and in this log the pointer was accurate while the value it implied was wrong.

Provenance is therefore `unknown`, which §4.4 caps at C0 on purpose. The verifier answers
`Available: none` and lists the eight fields that would have to exist.

## After

The same two decisions, re-emitted through the Reckon SDK. The Data API push is now
expressible: one record says `provenance: bundled, resolved: 0.0015`, the other says
`provenance: runtime_override, resolved: 0.0025`. Their `path_digest` values differ.

The run verifies at C2.

## What this does not show

It does not show C3. Neither of these decisions perturbs state the other reads, so no
counterfactual here crosses the cliff. When one does, `reckon boundary` reports the edge at
which evidence ends and labels everything past it hypothesis — it does not certify it, and
nor should any other tool.

It also does not show recovery of decision semantics from an uninstrumented system. The
"before" mapping was written by hand, by someone who already knew what the answer was. That
is out of scope by design (§6), and pretending otherwise would repeat the exact failure this
format exists to name.
