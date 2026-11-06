# Evaluation protocol

Use the held-out launcher with an exported or merged model checkpoint:

```bash
EVAL_MODEL_PATH=checkpoints/exported/model \
CONFIG_FILE=configs/train.env \
bash evaluation/evaluate_simrec.sh
```

`EVAL_DATA` defaults to `TEST_DATA`. The launcher runs validation-only rollouts:
it performs no optimizer step and forces target injection off. Supplying
`EVAL_DATA` is appropriate only for a separate held-out split.

Report instance-weighted NDCG@100 and Recall@100 from natural, non-redundant
Top-100 searches. For agent sessions, use the best eligible search turn. Report
Hit@1 according to whether the final recommendation belongs to the task target
set. Do not compare checkpoints evaluated with different task splits, indexes,
retrievers, simulator settings, or seeds.
