#!/usr/bin/env bash
# Run public, data-free release checks from any working directory.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q SimRec
bash -n scripts/train_simrec.sh
bash -n evaluation/evaluate_simrec.sh
git diff --check
