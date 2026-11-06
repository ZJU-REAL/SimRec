#!/usr/bin/env bash
# Summarize numeric metrics from a locally exported evaluation JSONL file.
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: bash analysis/summarize_metrics.sh <evaluation-metrics.jsonl>" >&2
  exit 2
fi

python3 - "$1" <<'PY'
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

path = Path(sys.argv[1])
metric_names = {
    "ndcg_at_100",
    "retrieval_ndcg_at_100",
    "recall_at_100",
    "recall_at_k",
    "hit_at_1",
    "recommend_hit_at_1",
}
values = defaultdict(list)
injected_rows = 0
rows = 0

def visit(value):
    global injected_rows
    if isinstance(value, dict):
        if value.get("target_injected") is True:
            injected_rows += 1
        for key, child in value.items():
            if key in metric_names and isinstance(child, (int, float)) and math.isfinite(child):
                values[key].append(float(child))
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)

for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    rows += 1
    visit(json.loads(line))

print(f"rows: {rows}")
print(f"target_injected=true markers: {injected_rows}")
for name in sorted(values):
    series = values[name]
    print(f"{name}: mean={sum(series) / len(series):.6f} n={len(series)}")
PY
