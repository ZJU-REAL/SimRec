from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from SimRec.simulator import clean_text
from SimRec.user_preference_profile import (
    LLMProfileConfig,
    filter_history,
    generate_llm_user_preference,
    load_user_histories,
)


DEFAULT_SOURCE = None
DEFAULT_PROFILE_SOURCES = ""
DEFAULT_OUTPUT_DIR = "data/processed/amazon_c4"


def _load_rows(source: str, split: str) -> list[dict[str, Any]]:
    if source.endswith(".jsonl"):
        with open(source, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if source.endswith(".csv"):
        with open(source, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError("Install `datasets` or pass a local .csv/.jsonl Amazon-C4 export.") from exc

    ds = load_dataset(source, split=split)
    return [ds[i] for i in range(len(ds))]


def _split_profile_sources(profile_sources: str | None) -> list[str]:
    if not profile_sources:
        return []
    return [source.strip() for source in profile_sources.split(",") if source.strip()]


def _build_example(
    row: dict[str, Any],
    user_histories: dict[str, list[dict[str, Any]]] | None = None,
    profile_config: LLMProfileConfig | None = None,
    profile_prompt_history_k: int = 30,
    profile_cache: dict[tuple[str, str], str] | None = None,
) -> dict[str, Any] | None:
    query = clean_text(row.get("query"))
    review = clean_text(row.get("ori_review"))
    item_id = clean_text(row.get("item_id"))
    if not query or not review or not item_id:
        return None
    user_id = clean_text(row.get("user_id"))
    example = {
        "qid": str(row.get("qid", "")),
        "source": "McAuley-Lab/Amazon-C4",
        "user_id": user_id,
        "target_item_id": item_id,
        "reference_review": review,
        "reference_query": query,
    }
    if user_histories is not None:
        history = filter_history(user_histories.get(user_id, []), exclude_qid=str(row.get("qid", "")), exclude_item_id=item_id)
        if history:
            if profile_config is None:
                raise ValueError(
                    "Profile histories were supplied, but no LLM profile configuration was provided. "
                    "Set SIMREC_PROFILE_LLM_BASE_URL, SIMREC_PROFILE_LLM_MODEL, and SIMREC_PROFILE_LLM_API_KEY."
                )
            cache_key = (user_id, item_id.upper())
            if profile_cache is not None and cache_key in profile_cache:
                profile = profile_cache[cache_key]
            else:
                profile = generate_llm_user_preference(history, profile_config, max_history=profile_prompt_history_k)
                if profile_cache is not None:
                    profile_cache[cache_key] = profile
            # Do not store raw purchase history in the released training data.
            example["user_preference"] = profile
            example["user_profile_status"] = "found"
            example["user_profile_generator"] = "llm"
        else:
            example["user_profile_status"] = "missing"
            example["user_profile_generator"] = "missing"
    return example


def main(
    source: str = DEFAULT_SOURCE,
    split: str = "train",
    output_dir: str = DEFAULT_OUTPUT_DIR,
    train_ratio: float = 0.90,
    validation_ratio: float = 0.05,
    test_ratio: float = 0.05,
    seed: int = 42,
    max_samples: int | None = None,
    profile_sources: str | None = DEFAULT_PROFILE_SOURCES,
    profile_max_history: int = 50,
    profile_prompt_history_k: int = 30,
    profile_config: LLMProfileConfig | None = None,
) -> None:
    ratios = (train_ratio, validation_ratio, test_ratio)
    if any(ratio < 0.0 for ratio in ratios) or abs(sum(ratios) - 1.0) > 1e-8:
        raise ValueError("train_ratio, validation_ratio, and test_ratio must be non-negative and sum to 1.0")

    rows = _load_rows(source, split)
    if max_samples is not None:
        rows = rows[:max_samples]

    profile_source_list = _split_profile_sources(profile_sources)
    user_histories = None
    if profile_source_list:
        user_histories = load_user_histories(profile_source_list, max_history=profile_max_history)
        print(f"Loaded user histories for {len(user_histories)} users from {len(profile_source_list)} profile source(s)")

    profile_cache: dict[tuple[str, str], str] = {}
    examples = [
        item
        for row in rows
        if (
            item := _build_example(
                row,
                user_histories=user_histories,
                profile_config=profile_config,
                profile_prompt_history_k=profile_prompt_history_k,
                profile_cache=profile_cache,
            )
        )
        is not None
    ]

    # Keep all records for a qid in one split so repeated task instances do
    # not leak between training, validation, and the final held-out test set.
    groups: dict[str, list[dict[str, Any]]] = {}
    for index, example in enumerate(examples):
        qid = clean_text(example.get("qid"))
        group_key = f"qid:{qid}" if qid else f"row:{index}"
        groups.setdefault(group_key, []).append(example)
    grouped_examples = list(groups.values())
    random.Random(seed).shuffle(grouped_examples)

    train_target = int(len(examples) * train_ratio)
    validation_target = train_target + int(len(examples) * validation_ratio)
    train_examples: list[dict[str, Any]] = []
    validation_examples: list[dict[str, Any]] = []
    test_examples: list[dict[str, Any]] = []
    for group in grouped_examples:
        if len(train_examples) < train_target:
            train_examples.extend(group)
        elif len(train_examples) + len(validation_examples) < validation_target:
            validation_examples.extend(group)
        else:
            test_examples.extend(group)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "train.jsonl"
    validation_path = out_dir / "validation.jsonl"
    test_path = out_dir / "test.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for item in train_examples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with validation_path.open("w", encoding="utf-8") as f:
        for item in validation_examples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with test_path.open("w", encoding="utf-8") as f:
        for item in test_examples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Wrote {len(train_examples)} train rows to {train_path}")
    print(f"Wrote {len(validation_examples)} validation rows to {validation_path}")
    print(f"Wrote {len(test_examples)} test rows to {test_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare Amazon-C4 data for SimRec.")
    parser.add_argument("--source", required=True, help="Path to an Amazon-C4 export or datasets identifier.")
    parser.add_argument("--split", default="train")
    parser.add_argument("--output_dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train_ratio", type=float, default=0.90)
    parser.add_argument("--validation_ratio", type=float, default=0.05)
    parser.add_argument("--test_ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument(
        "--profile_sources",
        default=DEFAULT_PROFILE_SOURCES,
        help="Comma-separated Amazon/profile JSONL or JSON files used to precompute each sample's user_profile.",
    )
    parser.add_argument(
        "--profile_max_history",
        type=int,
        default=50,
        help="Maximum history entries to store per user profile; use 0 to keep all available history.",
    )
    parser.add_argument(
        "--profile_prompt_history_k",
        type=int,
        default=30,
        help="Most recent chronological history entries supplied to the LLM profile prompt.",
    )
    parser.add_argument("--profile_llm_base_url", default=None, help="OpenAI-compatible profile LLM endpoint.")
    parser.add_argument("--profile_llm_model", default=None, help="Profile LLM model name.")
    parser.add_argument("--profile_llm_api_key", default=None, help="Profile LLM API key; prefer the environment variable.")
    parser.add_argument("--profile_llm_max_tokens", type=int, default=None)
    parser.add_argument("--profile_llm_temperature", type=float, default=None)
    parser.add_argument("--profile_llm_timeout", type=float, default=None)
    parser.add_argument("--profile_llm_max_retries", type=int, default=None)
    args = parser.parse_args()
    profile_config = None
    if args.profile_sources:
        env_config = LLMProfileConfig.from_env()
        profile_config = LLMProfileConfig(
            base_url=args.profile_llm_base_url if args.profile_llm_base_url is not None else env_config.base_url,
            model=args.profile_llm_model if args.profile_llm_model is not None else env_config.model,
            api_key=args.profile_llm_api_key if args.profile_llm_api_key is not None else env_config.api_key,
            max_tokens=args.profile_llm_max_tokens if args.profile_llm_max_tokens is not None else env_config.max_tokens,
            temperature=args.profile_llm_temperature if args.profile_llm_temperature is not None else env_config.temperature,
            timeout=args.profile_llm_timeout if args.profile_llm_timeout is not None else env_config.timeout,
            max_retries=args.profile_llm_max_retries if args.profile_llm_max_retries is not None else env_config.max_retries,
            seed=env_config.seed,
        )
        profile_config.validate()

    main(
        source=args.source,
        split=args.split,
        output_dir=args.output_dir,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        max_samples=args.max_samples,
        profile_sources=args.profile_sources,
        profile_max_history=args.profile_max_history,
        profile_prompt_history_k=args.profile_prompt_history_k,
        profile_config=profile_config,
    )
