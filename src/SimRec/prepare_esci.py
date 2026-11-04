"""Prepare qid-disjoint SimRec splits from an ESCI judgement export.

The input may be CSV or JSONL.  It must provide a query, a query identifier,
an item/product identifier, and an ESCI relevance label.  Exact and Substitute
labels become the multi-target relevance set for one recommendation task.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from SimRec.simulator import clean_text


DEFAULT_OUTPUT_DIR = "data/processed/esci"
POSITIVE_LABELS = {"E", "EXACT", "S", "SUBSTITUTE"}


def _load_rows(source: str) -> list[dict[str, Any]]:
    path = Path(source)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    raise ValueError("--source must be a .csv or .jsonl ESCI judgement export")


def _field(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = clean_text(row.get(name))
        if value:
            return value
    return ""


def _positive(label: str) -> bool:
    return clean_text(label).upper() in POSITIVE_LABELS


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def prepare(
    source: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    train_ratio: float = 0.90,
    validation_ratio: float = 0.05,
    test_ratio: float = 0.05,
    seed: int = 42,
) -> dict[str, int]:
    ratios = (train_ratio, validation_ratio, test_ratio)
    if any(ratio < 0 for ratio in ratios) or abs(sum(ratios) - 1.0) > 1e-8:
        raise ValueError("split ratios must be non-negative and sum to 1")

    grouped: dict[str, dict[str, Any]] = {}
    for row in _load_rows(source):
        qid = _field(row, "query_id", "qid", "query-id")
        query = _field(row, "query", "reference_query", "query_text")
        item_id = _field(row, "product_id", "item_id", "asin", "product_asin")
        label = _field(row, "esci_label", "label", "relevance_label")
        if not qid or not query or not item_id or not _positive(label):
            continue
        task = grouped.setdefault(
            qid,
            {
                "qid": qid,
                "source": "ESCI",
                "reference_query": query,
                "target_item_ids": [],
            },
        )
        if item_id.upper() not in {candidate.upper() for candidate in task["target_item_ids"]}:
            task["target_item_ids"].append(item_id.upper())

    tasks = list(grouped.values())
    random.Random(seed).shuffle(tasks)
    train_cutoff = int(len(tasks) * train_ratio)
    validation_cutoff = train_cutoff + int(len(tasks) * validation_ratio)
    splits = {
        "train": tasks[:train_cutoff],
        "validation": tasks[train_cutoff:validation_cutoff],
        "test": tasks[validation_cutoff:],
    }
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        _write_jsonl(destination / f"{name}.jsonl", rows)
    summary = {name: len(rows) for name, rows in splits.items()}
    print(json.dumps({"source": source, "output_dir": str(destination), **summary}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Local ESCI CSV or JSONL judgement export.")
    parser.add_argument("--output_dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train_ratio", type=float, default=0.90)
    parser.add_argument("--validation_ratio", type=float, default=0.05)
    parser.add_argument("--test_ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    prepare(
        source=args.source,
        output_dir=args.output_dir,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
