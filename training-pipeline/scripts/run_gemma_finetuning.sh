#!/usr/bin/env bash
# scripts/run_gemma_finetuning.sh

set -euo pipefail

CONFIG=${CONFIG:-configs/config.yaml}
HF_TOKEN=${HF_TOKEN:?"Set HF_TOKEN env var"}

echo "==> Starting Gemma-3n Fine-tuning"
python -m src.finetuning.gemma_finetuner \
  --config "$CONFIG" \
  --hf_token "$HF_TOKEN"
