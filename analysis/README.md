# Analysis

Analysis in this release is protocol-first: generated tables, plots, and
session records stay local under `analysis/outputs/`, which is ignored by Git.

[`summarize_metrics.sh`](summarize_metrics.sh) reads a locally exported JSONL
metrics file, reports common retrieval/final-hit aggregates, and counts any
`target_injected=true` markers. Use it only for inspection; reported evaluation
metrics must come from target-injection-disabled rollouts.

The paper analyses recovery after rejected recommendations, tool-use behavior,
candidate reranking, simulator choice, and component/reward ablations. Recreate
each analysis only from held-out trajectories produced with target injection
disabled. Preserve the run configuration and split identifier with every
aggregate; never store raw user histories or item-level private records here.
