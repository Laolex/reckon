# RCDR v0.1 — Replay-Complete Decision Record

Version: 0.1
Date: 2026-07-28
Status: specification, derived in-window (Rampamble, 2026-07-25 – 2026-08-02) from the
OPA, LangGraph, Hyperliquid and Polymarket capture probes.

> **On the name.** "Replay-complete" does not mean complete in the absolute. It means a
> record carries enough evidence to be complete *for a declared capability class*. A record
> is never sound on its own; it is sound for a stated counterfactual under a stated
> execution model. The format exists to make that statement checkable.

**Destination:** this document is a published artifact, not a planning note. When the
product repository is created it moves to `docs/RCDR-v0.1.md` and is versioned with the
SDK. It is kept in the planning directory only until that repository exists.

---

## 1. The problem this format solves

Four independent systems were probed. Every one of them produced records that looked
sufficient and were not:

| System | Highest class supported | Why it stops there |
|---|---|---|
| rr / Pernosco | C0 | records syscall results, not predicate structure |
| Hyperliquid agent log | < C1 | compared value never recorded; policy env-overridden |
| Polymarket signals log | cannot reach C2 | taken-only; rejected candidates absent |
| LangGraph checkpoint-sqlite | < C1 | threshold in zero persisted bytes; gates indistinct |
| OPA — config inside bundle roots | C1 | input plus resolved-via-bundle |
| OPA — config outside bundle roots | C1 but **undetectable** | identical input and revision produced opposite decisions |

The last row is the finding the format is built around. A sound engine, versioned bundles
and complete decision logs still lost C1 because one deployment choice — config pushed via
the Data API, outside the bundle's provenance boundary — sat outside the recorded evidence,
**and nothing in the record revealed which regime was in force.**

Two consequences follow, and they drive every requirement below:

1. **Replay soundness is not compositional.** It is a property of the whole execution path,
   not of any component. Versioning the parts does not version the path.
2. **A record must be able to admit its own ignorance.** A record that cannot express
   "I do not know where this value came from" will silently claim a class it cannot support.

---

## 2. Model

A **decision** is one evaluation of a predicate that admits or rejects an action.

A **record** describes one decision. A **run** is an ordered set of records sharing a
`run_id`.

Soundness is a property of the tuple:

```
soundness = f(record, counterfactual class, execution model)
```

The same bytes are sound for one counterfactual and undefined for another. The Hyperliquid
log supports replaying a tightening policy and cannot support a loosening one — identical
record, two different answers. Therefore a verifier reports a **capability class**, never a
percentage. A percentage is a scalar over incommensurable things and manufactures exactly
the false confidence this format exists to expose.

Soundness deliberately says nothing about the consequences of acting on a replay. Whether an
effect can be undone has no bearing on whether a replay is deductive. That is a separate
relation, defined in §3.1.

---

## 3. Capability classes

Classes are capabilities, not levels. Higher is not better; it is a different guarantee
with a strictly larger capture requirement.

### C0 — Identity Replay
Re-run what happened and reproduce the recorded decision.
**Requires:** the inputs each decision read, and a pinned execution model.

### C1 — Tightening Replay
Re-adjudicate under a policy admitting strictly fewer actions.
**Additionally requires, for every taken decision:** predicate identity, the value it
compared, and the *resolved* policy value in force at call time — the value itself, never a
pointer, version tag or bundle revision.
**Certifiable sound.**

### C2 — Loosening Replay
Re-adjudicate under a policy admitting more actions.
**Additionally requires:** the candidate set considered and rejected, with their compared
values, and an explicit declaration that the set is exhaustive.
This is the survivorship boundary: taken-only records can never reach C2, because the
admitted candidates do not exist in the log.
**Certifiable sound.**

### C3 — State-Coupled Replay — the cliff
A changed decision perturbs state that later decisions read.
**Additionally requires:** the dependency structure — what each decision read, and which
predicate consumed it.
**Not certifiable sound by anyone, ever.** Past the first decision whose change flips a
downstream predicate, the output is counterfactual inference, not replay. It stops being
evidence.

**The structural result.** C0–C2 are deductive given the right capture. C3 is not deductive
for anyone. So the honest top guarantee is: *certify soundness through C2; for C3, certify
where the evidence ends and hypothesis begins.* Inside a C3 counterfactual the divergence is
a stain through the dependency graph, per counterfactual — not a global verdict and not a
time horizon.

---

## 3.1 Admissibility — what a class licenses

A class states what the evidence supports. It does not state what a system may do with it.
Those are two relations, and this format keeps them apart:

```
soundness     = f(record, counterfactual class, execution model)   — computed by a verifier
admissibility = g(soundness class, reversibility of the action)    — decided by the consumer
```

The rule:

> **A replay may authorize an action only when it is deductive at the class that action
> requires. Below that class a replay may inform but never authorize, and an irreversible
> action is refused rather than downgraded.**

| Available class | Reversible action | Irreversible action |
|---|---|---|
| C0 | Authorize re-execution of what happened | Authorize re-execution of what happened |
| C1 | Authorize under a strictly tighter policy | Authorize under a strictly tighter policy |
| C2 | Authorize under a looser policy | Authorize under a looser policy |
| C3 | **Inform** — may propose, rank or prefill; a human or a deterministic gate decides | **Refuse** — no authorization path exists; the output is hypothesis |
| Below the requested class | Inform, and report the missing evidence | Refuse |

Two properties are load-bearing:

- **Demotion only.** Nothing may raise the admissible class — not a capture heuristic, and not
  a model's stated confidence. Evidence can be missing; it cannot be inferred into existence.
  This is the consuming-side form of the claim that no record carries its own soundness proof.
- **Never gate on self-confidence.** The inputs to `g` are the verifier's class and the action's
  reversibility. A confidence score is the quantity that most resembles evidence without being
  evidence — the consuming-side twin of the percentage §2 refuses to emit.

**Reversibility** is declared by the host system, not derived by RCDR. An action is *reversible*
if its effect can be undone by the same system, without a counterparty's consent, within a
stated window. Everything else is *irreversible*, including effects that are nominally undoable
but whose observation is not — a sent message, a published price, a released payout. An
unlabeled action is irreversible, for the same reason an unestablished provenance is `unknown`
and an unestablished candidate set is `taken_only`: every unknown in this format resolves toward
less claimed capability.

---

## 4. Record schema

JSON object. Unknown fields are ignored by conforming verifiers. Fields marked **required
for CN** are what the verifier checks when that class is requested.

### 4.1 Envelope

| Field | Type | Notes |
|---|---|---|
| `rcdr_version` | string | `"0.1"` |
| `decision_id` | string | unique within the run |
| `run_id` | string | groups decisions from one execution |
| `sequence` | integer | monotonic order within the run |
| `ts` | RFC 3339 string | informational; ordering comes from `sequence` |

### 4.2 Predicate — required for C1

| Field | Type | Notes |
|---|---|---|
| `predicate.id` | string | **content hash of the canonical predicate structure** — operator plus operand identities. Not a source location and not a name. |
| `predicate.operator` | string | e.g. `gte`, `lt`, `in`, `matches` |
| `predicate.expression` | string | canonical rendering, for humans |
| `predicate.location` | object | file/line, **informational only** |

`predicate.id` is a structural hash rather than a location because the LangGraph probe
showed two gates that were indistinguishable in the record while behaving differently. A
name or a line number does not survive a refactor and does not distinguish two gates that
look alike; the structure does.

### 4.3 Compared value — required for C1

| Field | Type | Notes |
|---|---|---|
| `compared.value` | any | the actual value the predicate evaluated |
| `compared.type` | string | declared type |

The Hyperliquid log recorded the decision and the threshold but never the compared value,
which is why it cannot reach C1. Recording the outcome without the operand records that a
decision happened, not why.

### 4.4 Policy — required for C1

| Field | Type | Notes |
|---|---|---|
| `policy.key` | string | identifier of the governing setting |
| `policy.resolved_value` | any | **the value in force at call time.** A pointer, version tag or bundle revision does not satisfy this field. |
| `policy.resolution.provenance` | enum | `bundled` \| `runtime_override` \| `environment` \| `computed` \| `unknown` |
| `policy.resolution.source` | string | where it resolved from, in whatever terms the host system uses |
| `policy.resolution.revision` | string | optional, informational |

**`provenance: unknown` caps the record at C0.** This is the direct fix for the OPA finding:
the failure was not that the config was overridden, it was that the record could not say so.
A format that has no way to express "I do not know where this came from" will emit records
that silently claim C1. Emitters must set `unknown` when they cannot establish provenance,
and verifiers must refuse C1 on it. Being wrong loudly is the requirement.

### 4.5 Outcome

| Field | Type | Notes |
|---|---|---|
| `outcome` | enum | `admit` \| `reject` |
| `action.id` | string | the action admitted or rejected |
| `action.params_digest` | string | digest of parameters; the format never requires raw parameters |

### 4.6 Candidates — required for C2

| Field | Type | Notes |
|---|---|---|
| `candidates.completeness` | enum | `exhaustive` \| `partial` \| `taken_only` |
| `candidates.items[]` | array | one per candidate considered |
| `candidates.items[].action_id` | string | |
| `candidates.items[].compared_value` | any | required for C2 |
| `candidates.items[].outcome` | enum | `admit` \| `reject` |
| `candidates.items[].predicate_id` | string | the predicate that judged this candidate |

**Absent `candidates.completeness` is interpreted as `taken_only`**, which is the
conservative reading and caps the record below C2. The Polymarket log is taken-only and
nothing in it says so; a reader must currently infer survivorship from absence. This field
makes survivorship a declared property rather than a discovered one.

### 4.7 Dependency structure — required for C3 boundary reporting

| Field | Type | Notes |
|---|---|---|
| `reads[]` | array | `{ key, value_digest, source }` |
| `writes[]` | array | `{ key, value_digest }` |

Present so a verifier can locate the C3 boundary. Their presence never certifies C3 — see
§3.

### 4.8 Execution model — required for C0

| Field | Type | Notes |
|---|---|---|
| `execution.runtime` | string | language and version |
| `execution.deps_digest` | string | digest of the resolved dependency set |
| `execution.path_digest` | string | **digest over the whole execution path**, including config resolution sources — not a composition of component versions |
| `execution.seed` | integer/null | RNG seed, null if the decision function is pure |
| `execution.clock` | string/null | injected time, null if unused |
| `execution.pure` | bool/null | the decision function is declared free of nondeterministic input. `true` satisfies C0's determinism requirement in place of a seed; `null` means undeclared and does **not** satisfy it |

`execution.pure` is a declaration, not a detection. Only the caller can know that a
decision function reads no clock, no RNG and no ambient state, so the emitter never infers
it — an undeclared decision without a seed fails C0, which is the correct default under the
same rule that makes absent `candidates.completeness` read as `taken_only`.

`execution.path_digest` exists because replay soundness is not compositional. Two runs with
identical component versions can differ; the path digest is what distinguishes them.

### 4.9 Capture metadata

| Field | Type | Notes |
|---|---|---|
| `capture.sdk_version` | string | |
| `capture.emitter` | string | which integration produced this |

---

## 5. Verifier contract

**Input:** a record (or a run) and a requested counterfactual class.
**Output:** the class supported, and if short, exactly which evidence is missing.

The report is type-error shaped, never a score:

```
Requested: Loosening Replay (C2)
Available: C1
Missing:   candidates.completeness = exhaustive
           candidates.items[].compared_value
```

### 5.1 Class computation

```
C0  ⟸  execution.runtime, execution.deps_digest, execution.path_digest present
        AND (execution.seed present OR decision declared pure)

C1  ⟸  C0
        AND predicate.id, compared.value, policy.resolved_value present
        AND policy.resolution.provenance ≠ unknown

C2  ⟸  C1
        AND candidates.completeness = exhaustive
        AND every candidates.items[] carries compared_value

C3  ⟸  never certified.
        Verifier returns the dependency edge at which evidence ends,
        and marks everything downstream as hypothesis.
```

### 5.2 Rules verifiers must obey

- Never emit a numeric score, confidence or percentage for a class.
- Never infer a missing field. A missing field is missing; best-effort substitution is how
  a record silently claims a class it cannot support.
- Never aggregate evidence (C0–C2) and hypothesis (past the C3 boundary) into one verdict.
- Report the class actually supported even when it is lower than requested — the useful
  output of a failed check is what to instrument next.

---

## 6. What this format does not do

- **No tamper evidence, no signatures, no anchoring.** The demonstrated threat is omission,
  not modification. Adding cryptography here would import a stack that solves none of the
  four capture failures the probes found.
- **No confidentiality.** Records may contain sensitive values; protecting them is the
  host system's problem.
- **No inference over uninstrumented systems.** RCDR describes what an instrumented emitter
  must produce. Recovering decision semantics from arbitrary code is a separate and much
  harder problem, deliberately out of scope.
- **No claim that C3 is achievable.** Any implementation that reports a C3 certification is
  non-conforming.
- **No classification of reversibility.** §3.1 consumes it; this format never infers it. The
  host declares which of its actions are reversible, and anything undeclared is irreversible.

---

## 7. Conformance

An **emitter** conforms at class CN if every record it produces satisfies CN's requirements
in §5.1, and it sets `provenance: unknown` and `completeness: taken_only` whenever it cannot
establish otherwise.

A **verifier** conforms if it implements §5.1 exactly and obeys every rule in §5.2.

Claiming "RCDR-conformant" without a class is meaningless. The claim is always
"RCDR v0.1, emitter conformant at C2".

---

## 8. Worked example

A record from a system whose config is pushed outside its bundle provenance boundary — the
OPA failure case, expressed in RCDR:

```json
{
  "rcdr_version": "0.1",
  "decision_id": "d-4192",
  "run_id": "r-88",
  "sequence": 17,
  "predicate": {
    "id": "p:9f3c1a…",
    "operator": "gte",
    "expression": "request.amount >= policy.limit"
  },
  "compared": { "value": 4200, "type": "number" },
  "policy": {
    "key": "policy.limit",
    "resolved_value": 5000,
    "resolution": { "provenance": "unknown", "source": "opa:data-api", "revision": "b-77" }
  },
  "outcome": "reject",
  "action": { "id": "transfer", "params_digest": "sha256:…" },
  "candidates": { "completeness": "taken_only", "items": [] },
  "execution": {
    "runtime": "go1.22",
    "deps_digest": "sha256:…",
    "path_digest": "sha256:…",
    "seed": null,
    "clock": null
  },
  "capture": { "sdk_version": "0.1.0", "emitter": "opa-sidecar" }
}
```

Verifier output:

```
Requested: Tightening Replay (C1)
Available: C0
Missing:   policy.resolution.provenance ≠ unknown
```

This is the entire point of the format. The same decision, under the old record shape,
would have been indistinguishable from a sound C1 record. Here it reports its own
insufficiency, and names the one field that would fix it.

---

## 9. Open questions for v0.2

- Whether `predicate.id` should hash operand *identities* or operand *types* — identities
  are stricter and may over-invalidate across benign refactors.
- Whether `candidates.completeness: partial` deserves an intermediate class between C1 and
  C2, or should simply fail C2. Currently it fails.
- How runs compose: whether a run-level class is the minimum over its records, or whether
  per-decision classes are the only meaningful unit. Currently per-decision.
- Whether `reads`/`writes` digests are sufficient to locate the C3 boundary, or whether the
  consuming predicate must be named explicitly at read time.
- Whether `reversibility` should become a declared field on the outcome object, so a run
  carries the input to §3.1's `g` instead of relying on the consumer to supply it out of band.
  Left out of v0.1 deliberately: the field is cheap to add and expensive to get wrong, and no
  probe evidence yet indicates which way it should go.
