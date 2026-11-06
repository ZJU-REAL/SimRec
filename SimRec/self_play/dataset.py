from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from SimRec.dataset import build_rec_system_prompt
from SimRec.simulator import clean_text


REC_SYSTEM_PROMPT = build_rec_system_prompt()


def build_rollout_messages() -> list[dict[str, str]]:
    return [{"role": "system", "content": REC_SYSTEM_PROMPT}]


class SimRecTaskDataset(Dataset):
    def __init__(self, entries, tokenizer, config):
        self.entries = list(entries)
        self.tokenizer = tokenizer
        self.config = config

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        row = dict(self.entries[idx])
        extra_info = row.get("extra_info") if isinstance(row.get("extra_info"), dict) else {}
        row["index"] = idx
        row["tools_kwargs"] = {}
        row["interaction_kwargs"] = dict(extra_info.get("interaction_kwargs") or {})
        row["is_validate"] = bool(extra_info.get("is_validate", False))
        row["dummy_tensor"] = torch.tensor([0], dtype=torch.uint8)
        return row


class SimRecDataset(Dataset):
    def __init__(self, data_files, tokenizer, processor, config, is_train: bool = True):
        if isinstance(data_files, str):
            data_files = [data_files]
        self.samples = []
        self.entries = []
        validate = not is_train
        for file_path in data_files:
            path = Path(file_path)
            if path.suffix != ".jsonl":
                raise ValueError(f"Unsupported data file format: {file_path}")
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        sample = json.loads(line)
                        reference_query = clean_text(sample.get("reference_query") or sample.get("problem"))
                        reference_review = clean_text(sample.get("reference_review") or sample.get("target_product"))
                        target_item_ids = self._normalize_target_item_ids(sample)
                        target_item_id = target_item_ids[0] if target_item_ids else ""
                        if reference_query and target_item_id:
                            sample["reference_query"] = reference_query
                            sample["reference_review"] = reference_review
                            sample["target_item_id"] = target_item_id
                            sample["target_item_ids"] = target_item_ids
                            sample_curriculum = sample.get("curriculum") if isinstance(sample.get("curriculum"), dict) else {}
                            user_preference = clean_text(sample.get("user_preference"))
                            user_profile_status = clean_text(sample.get("user_profile_status"))
                            self.samples.append(sample)
                            dialogue: list[dict[str, str]] = []
                            prompt = f"{REC_SYSTEM_PROMPT}\nThe shopper will speak first.\n"
                            self.entries.append(
                                {
                                    "prompt": prompt,
                                    "raw_prompt": build_rollout_messages(),
                                    "agent_name": "simrec_self_play_tool_agent",
                                    "env_context": {"dialogue": dialogue, "initial_role": "rec"},
                                    "data_source": "SimRec.self_play/recommender",
                                    "ability": "recommendation",
                                    "reward_model": {
                                        "style": "rule",
                                        "ground_truth": {
                                            "qid": sample.get("qid"),
                                            "source": sample.get("source", "McAuley-Lab/Amazon-C4"),
                                            "user_id": sample.get("user_id", ""),
                                            "target_item_id": target_item_id,
                                            "target_item_ids": target_item_ids,
                                            "target_ids": target_item_ids,
                                            "reference_review": reference_review,
                                            "reference_query": reference_query,
                                            "user_preference": user_preference,
                                            "user_profile_status": user_profile_status,
                                            "curriculum": sample_curriculum,
                                            "initial_state": {"dialogue": dialogue, "current_role": "rec"},
                                        },
                                    },
                                    "extra_info": {
                                        "qid": sample.get("qid"),
                                        "user_id": sample.get("user_id", ""),
                                        "curriculum": sample_curriculum,
                                        "role": "rec",
                                        "is_validate": validate,
                                        "interaction_kwargs": {
                                            "name": "simrec_self_play_user",
                                            "qid": sample.get("qid"),
                                            "user_id": sample.get("user_id", ""),
                                            "target_item_id": target_item_id,
                                            "target_item_ids": target_item_ids,
                                            "target_ids": target_item_ids,
                                            "reference_query": reference_query,
                                            "user_preference": user_preference,
                                            "user_profile_status": user_profile_status,
                                            "is_validate": validate,
                                        },
                                    },
                                }
                            )
        self.task_dataset = SimRecTaskDataset(self.entries, tokenizer, config)

    def __len__(self):
        return len(self.task_dataset)

    def __getitem__(self, idx):
        return self.task_dataset[idx]

    @staticmethod
    def _normalize_target_item_ids(sample: dict[str, Any]) -> list[str]:
        raw_targets = sample.get("target_item_ids")
        if raw_targets is None:
            raw_targets = sample.get("target_ids")
        if raw_targets is None:
            raw_targets = [sample.get("target_item_id") or sample.get("target_id")]
        if not isinstance(raw_targets, (list, tuple, set)):
            raw_targets = [raw_targets]

        targets: list[str] = []
        for item in raw_targets:
            item_id = clean_text(item).upper()
            if item_id and item_id not in targets:
                targets.append(item_id)
        return targets
