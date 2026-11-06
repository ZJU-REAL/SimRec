# Data construction

SimRec does not distribute source datasets, user histories, retrieval indexes,
or processed JSONL files. Download data from the original maintainers, accept
their terms, and place local files only under this directory. Everything except
the tracked `.gitkeep` markers and this documentation is ignored by Git.

## Source datasets

| Dataset | Official source | Role in SimRec |
|---|---|---|
| ESCI Shopping Queries Dataset | [amazon-science/esci-data](https://github.com/amazon-science/esci-data) | Query--product relevance judgements and catalog text for product-search tasks. |
| Amazon-C4 | [McAuley-Lab/Amazon-C4](https://huggingface.co/datasets/McAuley-Lab/Amazon-C4) | Complex first-person product requests paired with target items. |

Amazon-C4 is built on Amazon Reviews 2023. If constructing optional long-term
preference summaries, obtain the required review records from the authors'
[Amazon Reviews 2023 release](https://amazon-reviews-2023.github.io/) and comply
with its licence and access conditions. The public SimRec repository must never
include those records or derived raw histories.

## Local layout

```text
data/
├── raw/
│   ├── amazon_c4/             # Amazon-C4 download/export and optional local histories
│   └── esci/                  # ESCI judgement export and catalog source files
├── processed/
│   ├── amazon_c4/             # local train.jsonl, validation.jsonl, test.jsonl
│   └── esci/                  # local train.jsonl, validation.jsonl, test.jsonl
├── indexes/
│   ├── dense/                 # local dense index and metadata
│   └── bm25/                  # local BM25 index and metadata
└── profiles/                  # optional local one-sentence preference profiles
```

The preparation commands create task records, not retrieval indexes. Build an
index from catalog text using the same item-ID namespace as the task records,
then set `SEARCH_INDEX_DIR`, `SEARCH_BM25_INDEX_DIR`, and `SEARCH_MODEL_PATH`
in the local training configuration.

## Output record contract

Every processed row supplies a task identifier, an initial request, and at
least one target item:

```json
{
  "qid": "example-1",
  "source": "ESCI",
  "reference_query": "I need a compact travel charger.",
  "target_item_ids": ["ITEM_ID"]
}
```

`target_item_id` may be used instead of `target_item_ids` for a single-target
task. Amazon-C4 output additionally retains the original `reference_review`
locally. A `user_preference`, when present, is an LLM-generated one-sentence
summary; raw purchase-history records are not written to the processed output.

## ESCI construction

1. Download the official Shopping Queries Dataset from the link above. Select
   the desired locale and product categories before export; preserve a local
   record of this selection.
2. Export judgements to CSV or JSONL with a query ID (`query_id` or `qid`),
   `query`, item ID (`product_id` or `item_id`), and `esci_label`. The official
   release includes these fields along with product metadata.
3. Run the preparation command:

   ```bash
   python3 -m SimRec.prepare_esci \
     --source data/raw/esci/judgements.csv \
     --output_dir data/processed/esci \
     --seed 42
   ```

`prepare_esci` treats Exact (`E`) and Substitute (`S`) labels as targets,
groups all positive items by query ID, shuffles query groups deterministically,
and writes qid-disjoint 90/5/5 train/validation/test splits by default. It does
not download ESCI, select categories, or build catalog indexes. Because it
creates a local split, do not describe it as an upstream official ESCI split.

## Amazon-C4 construction

1. Download the official Amazon-C4 dataset card linked above and export the
   selected rows to CSV or JSONL. The preparation command requires `query`,
   `ori_review`, `item_id`, and `qid`; `user_id` is optional but required for
   optional profile construction.
2. Place the export at `data/raw/amazon_c4/` and create local qid-disjoint
   splits:

   ```bash
   python3 -m SimRec.prepare_amazon_c4 \
     --source data/raw/amazon_c4/amazon_c4.csv \
     --output_dir data/processed/amazon_c4 \
     --seed 42
   ```

Rows without a query, original review, or item ID are excluded. The script
keeps all rows for one `qid` together and produces deterministic 90/5/5 local
splits by default. Amazon-C4's upstream release is an evaluation dataset; this
repartitioning is a local training protocol and must be reported as such.

### Optional preference profiles

To construct profiles, pass one or more local history exports with
`--profile_sources`. For each task, the preparer removes the current target item
and task row from the history, chronologically orders the remaining records, and
asks an LLM for one short preference sentence. The only history-derived content
retained in the processed task record is that sentence and its generation
status; the task's source `user_id`, if present in Amazon-C4, remains local and
must not be committed.

```bash
export SIMREC_PROFILE_LLM_API_KEY='...'
python3 -m SimRec.prepare_amazon_c4 \
  --source data/raw/amazon_c4/amazon_c4.csv \
  --profile_sources data/raw/amazon_c4/reviews.jsonl \
  --output_dir data/processed/amazon_c4
```

Keep API credentials in the shell or an ignored local file. Do not commit the
history export, generated profiles, user IDs, or any raw review content.
