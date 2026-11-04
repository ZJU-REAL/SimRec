#!/usr/bin/env bash
# Run a held-out SimRec evaluation without an optimizer step.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# The train launcher owns all config parsing and validates the three-way split.
# EVAL_MODEL_PATH must be a loadable exported/merged model checkpoint.
export SIMREC_RUN_MODE=eval
exec bash "$repo_dir/scripts/train_simrec.sh"
