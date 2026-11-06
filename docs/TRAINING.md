# Training protocol

Run from the repository root after installing the package and its compatible
`verl` dependency:

```bash
cp configs/train.env.example configs/train.env
CONFIG_FILE=configs/train.env bash scripts/train_simrec.sh
```

`TRAIN_DATA`, `VAL_DATA`, and `TEST_DATA` must name three distinct JSONL files.
Only `TRAIN_DATA` is optimized on. During training, `VAL_DATA` is evaluated at
the configured validation interval; `TEST_DATA` is never passed to the trainer.
The checked-in template saves a checkpoint and evaluates `VAL_DATA` every 20
steps.

All paths in `configs/train.env.example` are repository-relative. Keep API keys
in the launching shell or a local ignored configuration file. Do not commit
datasets, histories, indexes, checkpoints, logs, or generated profiles.

The default paper-aligned settings are Qwen3-4B, Qwen3 Dense retrieval, eight
GRPO rollouts, learning rate `5e-7`, clipping coefficient `0.2`, KL coefficient
`1e-3`, a Top-100 search list with the Top-20 candidates visible, and two local
GPUs. Hardware-specific capacity settings may need adjustment.

Target injection is a training-only aid. It is eligible after two shopper turns
when the target is outside the visible candidate list. Natural results determine
the retrieval reward; the injected list must not be used to report retrieval
quality.
