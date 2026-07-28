# Demos

Three, all over real probe artifacts rather than fixtures written to make a point.

```
python -m demo.opa_replay          # a record that could not say where its policy came from
python -m demo.langgraph_replay    # a record that kept the reasoning and dropped the predicate
python -m demo.ablation            # does every field in the format earn its place?
```

Every claim below is asserted in `tests/`. If the arc is the argument, a regression in it is
a regression in the argument.

---

# 1. OPA — provenance

```
python -m demo.opa_replay
```

## What the evidence is

`evidence/opa-bundled2.log` is the decision log from a probe run against OPA v1.18.2 on
2026-07-16, using the Rego policy in `evidence/policy.rego` — a two-gate position-sizing
policy of the kind an autonomous trading agent runs, with both thresholds read from
`data.config` and therefore from outside the bundle's declared roots. It contains two
decisions:

| decision | input | bundle revision | engine | result |
|---|---|---|---|---|
| `ca4f88c4` | `raw_edge=0.002`, `equity=5000` | `policy-v2-code-only` | 1.18.2 | **trade** |
| `468228f8` | `raw_edge=0.002`, `equity=5000` | `policy-v2-code-only` | 1.18.2 | **skip** |

Identical input. Identical bundle revision. Identical engine version. Opposite decisions.

The log is unmodified. The only edit to `policy.rego` since the probe ran is to its comment
header, which referenced an internal file path; every rule is exactly as evaluated.

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

---

# 2. LangGraph — the missing predicate

```
python -m demo.langgraph_replay
```

## What the evidence is

`evidence/langgraph-checkpoints.sqlite` is the checkpointer output of the agent in
`evidence/langgraph_agent.py`, run on 2026-07-16 under three thread ids with different
values of `LG_MIN_EDGE_THRESHOLD`. The shape is the one most agent systems actually have: a
model produces evidence and a rationale, then code adjudicates that evidence against a
threshold read from the environment.

| thread | persisted rationale | outcome |
|---|---|---|
| `t1` | `ETH mispriced vs 4h mean; fair value 3006.00` | **skip** |
| `t2` | `ETH mispriced vs 4h mean; fair value 3006.00` | **trade** |
| `t3` | `ETH mispriced vs 4h mean; fair value 3006.00` | **skip** |

One rationale. Two outcomes.

Across all 12,286 bytes the checkpointer persisted, these occur **zero** times:
`LG_MIN_EDGE_THRESHOLD`, `0.0025`, `0.0015`, `threshold`, `net_edge`. Neither the value that
decided nor the value it was compared against is anywhere in the record.

> The record faithfully kept the reasoning that did not decide, and dropped the predicate
> that did.

This is the more common failure of the two. The OPA case needs an unusual deployment
choice; this one needs only an environment variable and a checkpointer doing exactly what it
was designed to do — persisting channel state, not the comparisons that produced it.

## Before

Mapped into RCDR, all three threads verify at `Available: none` against a C1 request. There
is no predicate structure to hash, no compared value, and no resolved policy.

## After

Re-emitted through the SDK with `provenance: environment` — an env-var threshold is not a
defect to hide, it is a fact the record has to be able to state. The run verifies at C2.

The load-bearing check is in `tests/test_demo_langgraph.py`: the re-emitted records
reproduce **all three observed outcomes**. That is what makes the "after" a reconstruction
rather than a story told over the top of the evidence.

---

# 3. Ablation — does every field earn its place?

```
python -m demo.ablation
```

Deletes each field from a record that supports C2 and re-runs the verifier. Output is
[`ABLATION.md`](ABLATION.md). **10 of 13 fields are load-bearing.** The three that are not
are named as decoration rather than defended, and `tests/test_ablation.py` fails if that set
ever changes silently.

A format is easy to pad. This is cheap to run only because §5.1 is a decision procedure, so
"what breaks" is computed rather than argued.
