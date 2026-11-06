#!/usr/bin/env bash
# Launch a paper variant using the local, ignored configuration file.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$repo_dir/scripts/train_simrec.sh"
