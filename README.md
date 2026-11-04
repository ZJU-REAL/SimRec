# SimRec

Reference implementation for **SimRec: Learning to Search, Ask, and Recommend from Simulated Interaction**.

SimRec trains a complete recommendation-agent policy with GRPO. The agent can search a catalog, inspect candidates, retrieve preference context, ask a clarification question, and revise a recommendation after feedback. It supports two task-anchored user simulators:

- `external`: an OpenAI-compatible LLM generates task-anchored shopper feedback.
- `self_play`: the rollout model alternates between shopper and recommender roles to generate interaction feedback without a separate simulator endpoint.

The reward combines the final hit, natural retrieval NDCG@100, parseable recommendation format, and one valid use of each tool type. Repeated queries receive no additional search bonus; unchanged post-feedback queries and long trajectories are penalized. Training-only target injection can prevent sparse-hit rollouts from providing no learning signal; it is disabled for validation by default.

## Install

Use a Python environment with a CUDA-compatible PyTorch build, then install [verl](https://github.com/volcengine/verl) and the extra dependencies:

```bash
pip install -r requirements.txt
git clone https://github.com/volcengine/verl.git ../verl
pip install -e .
pip install -e ../verl
export VERL_REPO_ROOT=../verl
```

The launcher expects this repository and `verl` to be sibling directories. Set
`VERL_REPO_ROOT` explicitly if your layout differs.

## Data

No datasets, checkpoints, model weights, API keys, or indexes are included. Prepare JSONL records with at least:

```json
{"qid":"example-1","target_item_id":"ITEM_ID","reference_query":"I need a compact travel charger."}
```

`target_item_ids` may be used instead of `target_item_id` for multi-target evaluation. The optional `user_preference` field must be a precomputed, one-sentence LLM profile; raw purchase histories are never exposed by the runtime preference tool.

To transform an Amazon-C4-style export, run from the repository root:

```bash
python3 -m SimRec.prepare_amazon_c4 \
  --source data/raw/amazon_c4/amazon_c4.csv \
  --output_dir data/processed/amazon_c4
```

To use the preference tool, provide target-filtered history files and configure
the profile LLM only in the environment. The preparation script calls that LLM
once per task profile, records `user_profile_generator: "llm"`, and writes only
the resulting profile sentence—not the raw history—to the output JSONL.

```bash
export SIMREC_PROFILE_LLM_API_KEY=...
python3 -m SimRec.prepare_amazon_c4 \
  --source data/raw/amazon_c4/amazon_c4.csv \
  --profile_sources data/raw/amazon_c4/reviews.jsonl \
  --output_dir data/processed/amazon_c4
```

For ESCI, download an official judgement export and build qid-disjoint splits:

```bash
python3 -m SimRec.prepare_esci \
  --source data/raw/esci/judgements.csv \
  --output_dir data/processed/esci
```

The ESCI source must contain query/query ID, item ID, and an ESCI label. Exact
and Substitute labels form each task's `target_item_ids`; build the matching
catalog index separately.

The preparation command produces qid-disjoint `train.jsonl`, `validation.jsonl`,
and `test.jsonl` files with the default 90/5/5 split. Build retrieval indexes
separately and set `SEARCH_INDEX_DIR` and `SEARCH_MODEL_PATH` in your local
configuration. Input data and indexes are intentionally ignored by Git.

The repository keeps only this directory layout; add generated or downloaded
files to their matching subdirectory rather than directly under `data/`:

```text
data/
├── raw/amazon_c4/             # downloaded source exports
├── processed/amazon_c4/       # train.jsonl, validation.jsonl, test.jsonl
├── raw/esci/                  # official ESCI judgement exports
├── processed/esci/            # prepared ESCI splits
├── indexes/dense/              # dense retrieval index and metadata
├── indexes/bm25/               # BM25 retrieval index
└── profiles/                   # optional precomputed preference profiles
```

## Train

Copy the relative-path template, then place any external-simulator credential only in the shell environment:

```bash
cp configs/train.env.example configs/train.env
export SIMREC_USER_LLM_API_KEY=...
CONFIG_FILE=configs/train.env bash scripts/train_simrec.sh
```

All paths in the template are relative to the repository root. Adjust the data
and index locations if your layout differs.

Set `SIMREC_USER_SIMULATOR_MODE=self_play` to use self-play. This changes the dataset, reward manager, interaction, tools, and agent loop together; no external user-simulator endpoint is needed.

## Held-out evaluation

Use a merged/exported checkpoint as `EVAL_MODEL_PATH`, then run the dedicated
validation-only launcher. It uses `TEST_DATA` exclusively as `data.val_files`;
verl constructs an inert dataset from `VAL_DATA` but performs no optimizer step.

```bash
EVAL_MODEL_PATH=checkpoints/exported/model \
CONFIG_FILE=configs/train.env \
bash scripts/evaluate_simrec.sh
```

Set `EVAL_DATA` only when evaluating a different held-out JSONL split. Target
injection is disabled automatically for these validation rollouts.

## Split policy

Use three different JSONL files: `TRAIN_DATA` is the only training input,
`VAL_DATA` is the only split evaluated during training, and `TEST_DATA` remains
held out. The launcher rejects overlapping files and never passes `TEST_DATA`
to verl. `SAVE_FREQ=20` and `VALIDATION_FREQ=20` save a checkpoint and evaluate
`VAL_DATA` every 20 steps; verl names the validation interval `trainer.test_freq`
internally.

The checked-in configuration matches the paper protocol: Qwen3-4B recommender, a natural top-100 retrieval list with the top 20 shown to the agent, and injection only in training after two shopper turns when the target is absent from those 20 candidates. Natural (uninjected) results alone determine retrieval reward. The external simulator defaults to Qwen3.6-Plus with temperature 0.2, 220 output tokens, and seed 42. GRPO uses eight rollouts, learning rate `5e-7`, temperature/top-p `1.0/1.0`, clipping `0.2`, and KL coefficient `1e-3`.

Use the same retrieval model, index, simulator settings, seed, and task split for all compared checkpoints. The simulator and profile-LLM OpenAI-compatible requests both include the configured seed (42 by default).

## Repository layout

- `src/SimRec/`: importable implementation package.
- `src/SimRec/self_play/`: shared-actor shopper/recommender path.
- `scripts/`: training and held-out evaluation launchers.
- `configs/`: portable, credential-free examples.
- `data/`: ignored dataset, index, and profile locations with tracked markers only.

## Privacy and release hygiene

This repository deliberately excludes local paths, user identifiers, raw datasets, models, retrieval indexes, checkpoints, logs, evaluation records, experiment trackers, and credentials. Before publishing, run the checks in the final section below and inspect `git status --ignored`.

```bash
python3 -m compileall -q src
rg -n -i '(sk-|api[_-]?key=)' . --glob '!README.md'
git status --short --ignored
```

The `rg` command should return no credential-like strings. Inspect configuration
files before every release and never commit a credential.
