#!/usr/bin/env bash
# scripts/run_t5_training.sh
# ──────────────────────────
# Launch T5 training with optional overrides via env vars.

set -euo pipefail

CONFIG=${CONFIG:-configs/config.yaml}
HF_TOKEN=${HF_TOKEN:?"Set HF_TOKEN env var"}

echo "==> Starting T5 Training"
python -m src.training.t5_trainer \
  --config "$CONFIG" \
  --hf_token "$HF_TOKEN"
