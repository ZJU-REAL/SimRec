from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MULTI_SPACE_RE = re.compile(r"\s+")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = MULTI_SPACE_RE.sub(" ", text.replace("\n", " "))
    return text.strip()


def compact_text(text: Any, limit: int = 200) -> str:
    compact = clean_text(text)
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def normalized_text_key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(text).lower())


def normalize_history_entry(row: dict[str, Any]) -> dict[str, Any] | None:
    user_id = clean_text(row.get("user_id"))
    if not user_id:
        return None

    if any(key in row for key in ("reference_query", "reference_review", "target_item_id")):
        return {
            "user_id": user_id,
            "qid": clean_text(row.get("qid")),
            "item_id": clean_text(row.get("target_item_id")).upper(),
            "query": clean_text(row.get("reference_query")),
            "review_text": clean_text(row.get("reference_review")),
            "title": clean_text(row.get("item_title") or row.get("title")),
            "category": clean_text(row.get("category") or row.get("main_category")),
            "rating": row.get("rating"),
            "timestamp": row.get("timestamp"),
            "verified_purchase": row.get("verified_purchase"),
            "source_type": "simrec",
        }

    if any(key in row for key in ("review_text", "item_title")):
        return {
            "user_id": user_id,
            "qid": clean_text(row.get("qid")),
            "item_id": clean_text(row.get("parent_asin") or row.get("asin")).upper(),
            "query": "",
            "review_text": clean_text(row.get("review_text")),
            "title": clean_text(row.get("item_title")),
            "category": clean_text(row.get("category") or row.get("main_category")),
            "rating": row.get("rating"),
            "timestamp": row.get("timestamp"),
            "verified_purchase": row.get("verified_purchase"),
            "source_type": "profile_history",
        }

    if any(key in row for key in ("asin", "parent_asin", "text", "title")):
        return {
            "user_id": user_id,
            "qid": "",
            "item_id": clean_text(row.get("parent_asin") or row.get("asin")).upper(),
            "query": "",
            "review_text": clean_text(row.get("text")),
            "title": clean_text(row.get("title")),
            "category": clean_text(row.get("category") or row.get("main_category")),
            "rating": row.get("rating"),
            "helpful_vote": row.get("helpful_vote"),
            "timestamp": row.get("timestamp"),
            "verified_purchase": row.get("verified_purchase"),
            "source_type": "amazon_review",
        }

    return None


def normalize_history_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    user_id = clean_text(row.get("user_id"))
    user_profile = row.get("user_profile")
    if user_id and isinstance(user_profile, dict):
        purchase_history = user_profile.get("purchase_history")
        if isinstance(purchase_history, list):
            entries = []
            for history_row in purchase_history:
                if not isinstance(history_row, dict):
                    continue
                normalized = normalize_history_entry({"user_id": user_id, **history_row})
                if normalized is not None:
                    entries.append(normalized)
            return entries

    normalized = normalize_history_entry(row)
    return [normalized] if normalized is not None else []


def history_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    try:
        timestamp_key = int(item.get("timestamp"))
    except Exception:
        timestamp_key = -1
    return timestamp_key, clean_text(item.get("qid")), clean_text(item.get("item_id")).upper()


def history_text(item: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            item.get("query", ""),
            item.get("review_text", ""),
            item.get("title", ""),
            item.get("category", ""),
        )
        if part
    ).strip()


def merge_history_items(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, ""):
            continue
        current = merged.get(key)
        if current in (None, ""):
            merged[key] = value
            continue
        if key == "review_text" and len(clean_text(value)) > len(clean_text(current)):
            merged[key] = value
        if (
            key == "title"
            and incoming.get("source_type") == "profile_history"
            and existing.get("source_type") != "profile_history"
        ):
            merged[key] = value
    return merged


def dedupe_and_sort_history(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        item_id = clean_text(item.get("item_id")).upper()
        timestamp = str(item.get("timestamp") or "")
        qid = clean_text(item.get("qid"))
        if item_id and timestamp:
            key = ("item_ts", item_id, timestamp)
        elif qid and item_id:
            key = ("qid_item", qid, item_id)
        else:
            key = ("text", qid, item_id, normalized_text_key(item.get("review_text", ""))[:120])
        if key in deduped:
            deduped[key] = merge_history_items(deduped[key], item)
        else:
            deduped[key] = item
    return sorted(deduped.values(), key=history_sort_key)


def load_user_histories(profile_sources: list[str], max_history: int = 0) -> dict[str, list[dict[str, Any]]]:
    profiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in profile_sources:
        path = Path(source).expanduser()
        if not path.exists():
            continue
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for user_id, value in data.items():
                entries = value.get("purchase_history") if isinstance(value, dict) else value
                if not isinstance(entries, list):
                    continue
                for row in entries:
                    if isinstance(row, dict):
                        profiles[user_id].extend(normalize_history_entries({"user_id": user_id, **row}))
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                for item in normalize_history_entries(row):
                    profiles[item["user_id"]].append(item)

    result = {}
    for user_id, items in profiles.items():
        history = dedupe_and_sort_history(items)
        if max_history > 0:
            history = history[-max_history:]
        result[user_id] = history
    return result


def filter_history(
    history: list[dict[str, Any]],
    exclude_qid: str | None = None,
    exclude_item_id: str | None = None,
) -> list[dict[str, Any]]:
    exclude_qid = clean_text(exclude_qid)
    exclude_item_id = clean_text(exclude_item_id).upper()
    return [
        item
        for item in history
        if (not exclude_qid or clean_text(item.get("qid")) != exclude_qid)
        and (not exclude_item_id or clean_text(item.get("item_id")).upper() != exclude_item_id)
    ]


LLM_USER_PROFILE_PROMPT = """Based on the user's purchase history below, generate a concise user preference profile.

## User Purchase History (chronological order):
{purchase_history}

## Statistics:
- Average rating: {avg_rating}

## Requirements:
1. Summarize the user's likely purchase preferences and favorite product types.
2. If low-rated items clearly indicate dislikes, mention that briefly.
3. Keep the profile to exactly one short natural sentence of 20-30 words.
4. Output ONLY in the <answer> tag, no other explanatory text.
5. Do not include unsupported details, user IDs, bullet points, or multiple sentences.

## Output Format:
<answer>
The user likely prefers practical, durable products in their favorite categories and avoids items with clear quality or usability issues.
</answer>"""


def _format_rating(value: Any) -> str:
    try:
        return f"{float(value):.1f}/5"
    except Exception:
        return "unknown"


def _history_line(item: dict[str, Any]) -> str:
    parts = []
    category = clean_text(item.get("category"))
    title = clean_text(item.get("title"))
    review = compact_text(item.get("review_text"), limit=180)
    query = compact_text(item.get("query"), limit=120)
    if category:
        parts.append(f"Category: {category}")
    if title:
        parts.append(f"Review title: {compact_text(title, limit=100)}")
    if item.get("rating") is not None:
        parts.append(f"Rating: {_format_rating(item.get('rating'))}")
    if query:
        parts.append(f"Need/query: {query}")
    if review:
        parts.append(f"Review: {review}")
    return "- " + " | ".join(parts) if parts else "- Unknown purchase"


def build_llm_profile_prompt(
    history: list[dict[str, Any]],
    max_history: int = 30,
) -> str:
    selected = sorted(history, key=history_sort_key)[-max(1, int(max_history)) :]
    purchase_history = "\n".join(_history_line(item) for item in selected) or "No purchase history available."
    ratings = []
    for item in selected:
        try:
            ratings.append(float(item.get("rating")))
        except Exception:
            continue
    avg_rating = f"{sum(ratings) / len(ratings):.1f}/5" if ratings else "unknown"
    return LLM_USER_PROFILE_PROMPT.format(purchase_history=purchase_history, avg_rating=avg_rating)


def parse_profile_answer(response_text: str) -> str | None:
    text = clean_text(response_text)
    match = re.search(r"<answer>(.*?)</answer>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        text = clean_text(match.group(1))
    text = re.sub(r"</?answer>", "", text, flags=re.IGNORECASE).strip()
    if not text:
        return None
    return text


def normalize_user_preference_text(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    if text.lower().startswith("user preference:"):
        prefix, body = text.split(":", 1)
        body = clean_text(body)
        return f"{prefix}: {body}"
    return f"User preference: {text}"


@dataclass(frozen=True)
class LLMProfileConfig:
    """Credential-free configuration for one-time profile generation."""

    base_url: str
    model: str
    api_key: str
    max_tokens: int = 96
    temperature: float = 0.2
    timeout: float = 60.0
    max_retries: int = 3
    seed: int = 42

    @classmethod
    def from_env(cls) -> "LLMProfileConfig":
        return cls(
            base_url=os.environ.get("SIMREC_PROFILE_LLM_BASE_URL", "").strip(),
            model=os.environ.get("SIMREC_PROFILE_LLM_MODEL", "").strip(),
            api_key=os.environ.get("SIMREC_PROFILE_LLM_API_KEY", "").strip(),
            max_tokens=int(os.environ.get("SIMREC_PROFILE_LLM_MAX_TOKENS", "96")),
            temperature=float(os.environ.get("SIMREC_PROFILE_LLM_TEMPERATURE", "0.2")),
            timeout=float(os.environ.get("SIMREC_PROFILE_LLM_TIMEOUT", "60")),
            max_retries=int(os.environ.get("SIMREC_PROFILE_LLM_MAX_RETRIES", "3")),
            seed=int(os.environ.get("SIMREC_PROFILE_LLM_SEED", "42")),
        )

    def validate(self) -> None:
        missing = [name for name, value in (("SIMREC_PROFILE_LLM_BASE_URL", self.base_url), ("SIMREC_PROFILE_LLM_MODEL", self.model), ("SIMREC_PROFILE_LLM_API_KEY", self.api_key)) if not value]
        if missing:
            raise ValueError("LLM profile generation requires " + ", ".join(missing))


def generate_llm_user_preference(
    history: list[dict[str, Any]],
    config: LLMProfileConfig,
    *,
    max_history: int = 30,
) -> str:
    """Summarize target-filtered chronological history with the configured LLM.

    This function intentionally has no heuristic fallback.  A generated profile
    is therefore always traceable to the LLM specified in the release config.
    """

    if not history:
        raise ValueError("Cannot generate an LLM profile from empty purchase history")
    config.validate()
    base_url = config.base_url.rstrip("/")
    endpoint = f"{base_url if base_url.endswith('/v1') else base_url + '/v1'}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "Generate one concise, evidence-grounded user preference profile."},
            {"role": "user", "content": build_llm_profile_prompt(history, max_history=max_history)},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "seed": config.seed,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = ""
    for attempt in range(max(1, config.max_retries)):
        try:
            request = Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
                method="POST",
            )
            with urlopen(request, timeout=config.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            choices = response_payload.get("choices") or []
            content = (choices[0].get("message") or {}).get("content") if choices else ""
            parsed = parse_profile_answer(str(content or ""))
            if parsed:
                return normalize_user_preference_text(parsed)
            last_error = "response did not contain a profile"
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, IndexError, KeyError) as exc:
            last_error = str(exc).replace("\n", " ")[:500]
        if attempt + 1 < max(1, config.max_retries):
            time.sleep(min(8.0, 1.5 * (2**attempt)))
    raise RuntimeError(f"LLM profile generation failed: {last_error or 'unknown error'}")


def render_user_profile_field(user_profile: Any) -> tuple[str, bool]:
    """Expose only an already-generated LLM profile to the recommendation agent."""

    if not isinstance(user_profile, str):
        return "User preference: No precomputed LLM preference profile is available.", False
    text = clean_text(user_profile)
    if not text or text.lower() in {"none", "null", "no prior history"}:
        return "User preference: No precomputed LLM preference profile is available.", False
    return normalize_user_preference_text(text), True
