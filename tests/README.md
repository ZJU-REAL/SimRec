# Tests

This directory is reserved for public, data-free tests. Release checks should
cover package importability, launcher syntax, relative-path handling, split
separation, and prompt/tool-output contracts. Do not add tests that require a
private dataset, live API credential, local checkpoint, or personal path.

The lightweight release checks are:

```bash
python3 -m compileall -q src
bash -n scripts/train_simrec.sh
bash -n evaluation/evaluate_simrec.sh
git diff --check
```
