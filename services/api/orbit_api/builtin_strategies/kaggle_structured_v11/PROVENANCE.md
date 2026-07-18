# Kaggle Structured Baseline v11 provenance

- Kaggle kernel: `pilkwang/orbit-wars-structured-baseline`
- Public source: <https://www.kaggle.com/code/pilkwang/orbit-wars-structured-baseline>
- Author: Pilkwang Kim
- Downloaded with Kaggle CLI: 2026-07-18
- Notebook SHA-256: `5018e7cfea6cd7187872d5f888d5c3f3c963d239c6b19ae8aa3081178f6d64fe`
- Extracted `submission.py` SHA-256: `9970e82718ccd1e290a0cdb7935b33dc0025e50d0058391299bc8fa712853c11`
- License basis: public Kaggle notebook code distributed through Meta Kaggle Code under Apache 2.0.

`main.py` is the unmodified concatenation of the notebook cells that write or append to
`submission.py`. `entrypoint.py` is a platform-owned adapter from Orbit/Wars' public object
observation to the row-based Kaggle competition observation. It also normalizes Kaggle's signed
angles to the public `0 <= angle < 2π` contract and applies the platform's six-command turn limit.

The import can be reproduced with:

```bash
kaggle kernels pull pilkwang/orbit-wars-structured-baseline -p /tmp/orbit-kaggle-template -m
sh scripts/python.sh scripts/import_kaggle_template.py \
  /tmp/orbit-kaggle-template/orbit-wars-structured-baseline.ipynb \
  services/api/orbit_api/builtin_strategies/kaggle_structured_v11/main.py \
  --metadata /tmp/orbit-kaggle-template/kernel-metadata.json
```
