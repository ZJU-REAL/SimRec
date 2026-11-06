# Analysis

Analysis in this release is protocol-first: generated tables, plots, and
session records stay local under `analysis/outputs/`, which is ignored by Git.

The paper analyses recovery after rejected recommendations, tool-use behavior,
candidate reranking, simulator choice, and component/reward ablations. Recreate
each analysis only from held-out trajectories produced with target injection
disabled. Preserve the run configuration and split identifier with every
aggregate; never store raw user histories or item-level private records here.
