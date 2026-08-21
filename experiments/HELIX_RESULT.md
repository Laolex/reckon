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
| `text-embedding-v3` ANN | 2.5% | 8.3% | 11.7% | R@20 23.3% | 0.0564 |
| BM25 | 2.5% | 7.5% | 12.5% | R@20 29.2% | 0.0588 |
| local ANN + BM25 RRF | 1.7% | 10.8% | 16.7% | R@40 37.5% | 0.0579 |
| semantic ANN + BM25 RRF | 3.3% | 10.0% | 16.7% | R@40 36.7% | 0.0742 |

Exact graph traversal recovered and validated all 120 recorded partners and relation
labels with zero mismatches. On the semantic run, median local query latency was
7.194 ms for ANN, 6.538 ms for BM25, and 4.452 ms for graph validation. Index activation
took 2.163 seconds and ingestion took 2.185 seconds on this machine.

The relation split is the more informative result. Semantic ANN improved contradiction
MRR from 0.0462 to 0.0793, while paraphrase MRR fell from 0.0491 to 0.0335. Semantic
hybrid RRF found 41.7% of exact contradiction partners by rank 40 and 31.7% of exact
paraphrase partners; the private baseline found 46.7% and 28.3%, respectively. These
movements are small and mixed. The semantic model changes ordering but does not turn
the corpus into a reliably retrievable relation set.

These retrieval figures measure recovery of the exact paired statement, not recovery
of every potentially relevant statement. The corpus does not label all cross-pair
relations, so treating another plausible hit as correct would manufacture ground truth
that the records do not contain.

## Boundary

The private ANN leg used a deterministic local feature-hash vector over word unigrams
and bigrams. The semantic leg was run after explicit authorization and sent 162 unique
recorded statements to DashScope's `text-embedding-v3` endpoint. Its embeddings and
results are cached separately from the private baseline.

The semantic result agrees with the earlier Reckon cosine probe without restating its
claim: `text-embedding-v3` changes candidate order but does not establish a relation.
In the earlier pairwise measurement, contradictions outranked paraphrases in 37.5% of
cross-class comparisons and no threshold separated them. Here, semantic exact-pair
retrieval was not materially better than BM25 or the local lexical vector.

Any future uncached semantic run would transmit the corpus again. The experiment refuses
to do that unless the caller passes both
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
