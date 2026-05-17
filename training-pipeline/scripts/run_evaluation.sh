#!/usr/bin/env bash
# scripts/run_evaluation.sh

set -euo pipefail

CONFIG=${CONFIG:-configs/config.yaml}
HF_TOKEN=${HF_TOKEN:?"Set HF_TOKEN env var"}
GEMINI_KEY=${GEMINI_KEY:-""}
MODELS=${MODELS:-"t5_finetuned t5_base"}

echo "==> Starting Evaluation Pipeline (models: $MODELS)"
python -m src.evaluation.evaluator \
  --config "$CONFIG" \
  --models $MODELS \
  --hf_token "$HF_TOKEN" \
  --gemini_key "$GEMINI_KEY"
