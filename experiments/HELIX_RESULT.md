# HelixDB retrieval experiment

The measured result is that HelixDB works well as a disposable projection over
Reckon's evidence, but it does not change what Reckon may certify. Search proposes
candidates; only recorded structure establishes a relation.

The experiment imported 120 relations derived from all 23 archived ClearCrew runs:
60 paraphrases and 60 opposite recorded verdicts citing the same policy rule. Each
side became a `Claim` node. A `RecordedRelation` node retained the source label and
the two claims linked to it through `IN_RECORDED_RELATION` edges. Reckon's JSONL
artifacts remained canonical.

## Result

The local run used the official `ghcr.io/helixdb/helixdb:v0.0.4` image in ephemeral
memory mode. It created BM25 and 1,024-dimensional vector indexes, waited for their
asynchronous activation, ingested the graph, ran 120 queries through each retrieval
path, and traversed every recorded relation.

| Path | R@1 | R@5 | R@10 | Widest measured recall | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| local lexical-hash ANN | 0.8% | 9.2% | 16.7% | R@20 25.0% | 0.0476 |
| BM25 | 2.5% | 7.5% | 12.5% | R@20 29.2% | 0.0588 |
| reciprocal-rank fusion | 1.7% | 10.8% | 16.7% | R@40 37.5% | 0.0579 |

Exact graph traversal recovered and validated all 120 recorded partners and relation
labels with zero mismatches. Median local query latency was 6.734 ms for ANN, 6.741 ms
for BM25, and 4.599 ms for graph validation. Index activation took 2.169 seconds and
ingestion took 2.180 seconds on this machine.

These retrieval figures measure recovery of the exact paired statement, not recovery
of every potentially relevant statement. The corpus does not label all cross-pair
relations, so treating another plausible hit as correct would manufacture ground truth
that the records do not contain.

## Boundary

The ANN leg used a deterministic local feature-hash vector over word unigrams and
bigrams. It validates HelixDB's vector-index plumbing without disclosing corpus text,
but it is not a semantic embedding and its recall must not be generalized to a semantic
model. The earlier Reckon cosine probe remains the semantic measurement: on
`text-embedding-v3`, contradictions outranked paraphrases in 37.5% of cross-class
comparisons and no threshold separated them.

Re-running semantic retrieval would send 162 unique recorded statements to DashScope.
The experiment refuses to do that unless the caller passes both
`--embedding-provider dashscope` and `--allow-third-party-corpus` after explicit
authorization.

## Consequence

HelixDB earns a place as an optional read model for investigation and presentation. It
does not belong in the canonical capture path. The graph can make a recorded evidence
relationship navigable and fast; it cannot promote similarity into evidence, repair a
missing predicate, or extend certification past Reckon's C2-to-C3 boundary.

Install the evaluation extra, then reproduce the privacy-preserving run with a
disposable HelixDB server on port 6970:

```bash
pip install -e '.[dev,helix-evaluation]'
docker run --rm --name reckon-helix-spike \
  -p 127.0.0.1:6970:8080 ghcr.io/helixdb/helixdb:v0.0.4
python experiments/helix_retrieval.py
```

Machine-readable output is written to `.artifacts/helix-results.json` and excluded
from version control.
