#!/usr/bin/env bash
# scripts/run_tinyllama_finetuning.sh

set -euo pipefail

CONFIG=${CONFIG:-configs/config.yaml}
HF_TOKEN=${HF_TOKEN:?"Set HF_TOKEN env var"}

echo "==> Starting TinyLlama Fine-tuning"
python -m src.finetuning.tinyllama_finetuner \
  --config "$CONFIG" \
  --hf_token "$HF_TOKEN"
