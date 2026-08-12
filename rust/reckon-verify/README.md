# reckon-verify

An independent, offline verifier for Reckon ledgers.

```
cargo build --release
./target/release/reckon-verify ledger.jsonl
```

Exit codes are the interface: `0` intact, `1` findings printed, `2` the file could not
be read or parsed. The third is deliberately separate — *"I could not check this"* and
*"this is broken"* are different claims, and a tool that collapses them asserts
something it does not know.

## Why a third implementation

Not speed. A record verified by code that shares nothing with the writer — no library,
no language, no author's assumptions — is verified by something that cannot inherit the
writer's mistake. Python writes, the browser verifier checks in a tab, this checks
offline with no runtime at all. Agreement across three is evidence. Agreement with
yourself is not.

## The hard part is canonicalisation, not hashing

Everything here exists to reproduce `json.dumps(value, sort_keys=True,
separators=(",", ":"))` byte for byte, including the parts nobody would choose:

- **Non-ASCII is escaped.** Python's `ensure_ascii` defaults to true, so `café`
  serialises as `café`. `serde_json::to_string` does not do this.
- **Escaping is per UTF-16 code unit, not per Unicode scalar.** U+1F9FE must become
  the surrogate pair `🧾`. Iterating `chars()` yields one escape instead of
  two, which hashes differently and silently — the exact class of bug a verifier
  exists to catch, reintroduced inside the verifier.
- **`/` is not escaped.** Escaping it produces valid JSON and the wrong bytes.
- **Keys sort by code point.** Rust's bytewise `str` ordering is the same order,
  because UTF-8 was designed so byte order equals code point order. That equivalence
  is load-bearing, so it is stated rather than relied on quietly.

`tests/parity.rs` shells out to the real `reckon` package and compares canonical form
and digest on the corpus chosen for exactly these disagreements. A fixture would freeze
today's behaviour and keep passing after Python changed; this fails.

## Two detectors, not one

`prev_hash` proves nothing was edited. `seq` proves nothing was *removed* — and a
chain with an interior record excised still links correctly across the gap if you only
check hashes. Both run, and both findings are reported separately.

Verified against the Python implementation on three ledgers — intact, tampered, and
excised — producing character-identical output in every case.
