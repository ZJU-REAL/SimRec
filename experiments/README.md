# Experiments

This directory records how public experiment recipes map to the portable
configuration template. It intentionally contains no run outputs, checkpoints,
or data-derived result files.

| Paper setting | Configuration change |
|---|---|
| External simulator (default) | `SIMREC_USER_SIMULATOR_MODE=external` |
| Shared-parameter self-play | `SIMREC_USER_SIMULATOR_MODE=self_play` |
| Dense retrieval (default) | `SIMREC_SEARCH_MODE=dense` and a dense index |
| BM25 variant | `SIMREC_SEARCH_MODE=bm25` and a BM25 index |
| Held-out evaluation | `EVAL_MODEL_PATH=... bash evaluation/evaluate_simrec.sh` |

Start from [`configs/train.env.example`](../configs/train.env.example). Record
the final resolved non-secret configuration, random seed, checkpoint identifier,
and evaluation split outside Git or in a future anonymized result manifest.
