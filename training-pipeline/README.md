# Spark2Scale — LLM Training, Fine-tuning & Evaluation Pipeline

> A structured, production-ready ML project for training and evaluating large language models on business QA tasks.  
> Covers **FLAN-T5-XL** (training), **Gemma-3n** and **TinyLlama** (fine-tuning), and a shared **evaluation pipeline** with 10+ metrics.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Models](#models)
- [Evaluation Metrics](#evaluation-metrics)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Docker](#docker)
- [Running Individual Pipelines](#running-individual-pipelines)
- [MLflow Tracking](#mlflow-tracking)
- [Tests](#tests)
- [Environment Variables](#environment-variables)

---

## Project Overview

Spark2Scale is an end-to-end ML pipeline for fine-tuning and evaluating LLMs on a business-focused QA dataset (`Dohahemdann/business-qa-analysis`). The project follows standard ML engineering conventions:

- **Single config file** (`configs/config.yaml`) controls all hyperparameters
- **Modular source layout** under `src/` with clean separation of training, fine-tuning, evaluation, and utilities
- **Dockerized** for GPU environments via `docker compose`
- **MLflow** experiment tracking baked into the Gemma pipeline
- **CLI entry points** for every pipeline stage

---

## Architecture

```
Notebooks (source)
      │
      ▼
┌─────────────────────────────────────────────────┐
│  configs/config.yaml  (single source of truth)  │
└─────────────────────────────────────────────────┘
      │
      ├── src/training/t5_trainer.py       ← FLAN-T5-XL + LoRA (4-bit QLoRA)
      │
      ├── src/finetuning/
      │     ├── gemma_finetuner.py         ← Gemma-3n-E2B-it + Unsloth + MLflow
      │     └── tinyllama_finetuner.py     ← TinyLlama-1.1B + LoRA (causal LM)
      │
      ├── src/evaluation/
      │     ├── metrics.py                 ← All 10+ metric functions
      │     ├── llm_judge.py              ← Gemini LLM-as-a-judge
      │     └── evaluator.py              ← Orchestrates full eval pipeline
      │
      └── src/utils/helpers.py             ← Logging, config, seed, device
```

---

## Directory Structure

```
spark2scale/
├── configs/
│   └── config.yaml              # All hyperparameters & model IDs
├── src/
│   ├── __init__.py
│   ├── training/
│   │   ├── __init__.py
│   │   └── t5_trainer.py        # T5 training pipeline
│   ├── finetuning/
│   │   ├── __init__.py
│   │   ├── gemma_finetuner.py   # Gemma-3n fine-tuning
│   │   └── tinyllama_finetuner.py  # TinyLlama fine-tuning
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── metrics.py           # All scoring functions
│   │   ├── llm_judge.py         # Gemini judge wrapper
│   │   └── evaluator.py         # Main evaluation orchestrator
│   └── utils/
│       ├── __init__.py
│       └── helpers.py           # Shared utilities
├── scripts/
│   ├── run_t5_training.sh
│   ├── run_gemma_finetuning.sh
│   ├── run_tinyllama_finetuning.sh
│   └── run_evaluation.sh
├── tests/
│   ├── test_metrics.py
│   └── test_config.py
├── outputs/                     # Auto-created; holds checkpoints, plots, CSVs
├── docs/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── requirements.txt
├── setup.py
└── README.md
```

---

## Models

| Model                     | Type      | Base                                 | Strategy                           |
| ------------------------- | --------- | ------------------------------------ | ---------------------------------- |
| **Spark2Scale T5**        | Seq2Seq   | `google/flan-t5-xl`                  | QLoRA 4-bit + LoRA (r=16)          |
| **Spark2Scale Gemma**     | Causal LM | `unsloth/gemma-3n-E2B-it`            | LoRA via Unsloth (r=8)             |
| **Spark2Scale TinyLlama** | Causal LM | `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | LoRA (r=16, all projection layers) |

All models are trained on `Dohahemdann/business-qa-analysis` — a business intelligence QA dataset.

---

## Evaluation Metrics

The evaluation pipeline computes all of the following for every model:

| Category         | Metric              | Description                                                           |
| ---------------- | ------------------- | --------------------------------------------------------------------- |
| **Speed**        | TTFT                | Time to first token                                                   |
| **Speed**        | TPOT                | Time per output token                                                 |
| **Speed**        | Throughput          | Tokens/second                                                         |
| **Quality**      | Cross-Entropy Loss  | Token-level loss                                                      |
| **Quality**      | Perplexity          | Exponential of CE loss                                                |
| **Faithfulness** | RAGAS Faithfulness  | Claim-level NLI entailment vs context                                 |
| **Faithfulness** | Hallucination Rate  | 1 – Faithfulness                                                      |
| **Text Quality** | METEOR              | Unigram recall with stemming & synonyms                               |
| **Text Quality** | G-Eval              | Heuristic structure + diversity + overlap                             |
| **Similarity**   | Semantic Similarity | Cosine similarity via `all-MiniLM-L6-v2`                              |
| **Diversity**    | Distinct-2          | Unique bigram ratio across responses                                  |
| **Diversity**    | Repetition Rate     | 1 – Distinct-2                                                        |
| **LLM Judge**    | Gemini Score (1-10) | Coherence, Consistency, Conciseness, Structure, Hallucination Freedom |

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/your-org/spark2scale.git
cd spark2scale
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env — add your HF_TOKEN and GEMINI_API_KEY
source .env
```

### 3. Run a pipeline

```bash
# T5 Training
python -m src.training.t5_trainer --config configs/config.yaml --hf_token $HF_TOKEN

# Gemma Fine-tuning
python -m src.finetuning.gemma_finetuner --config configs/config.yaml --hf_token $HF_TOKEN

# TinyLlama Fine-tuning
python -m src.finetuning.tinyllama_finetuner --config configs/config.yaml --hf_token $HF_TOKEN

# Evaluation (T5 fine-tuned vs T5 base)
python -m src.evaluation.evaluator \
  --config configs/config.yaml \
  --models t5_finetuned t5_base \
  --hf_token $HF_TOKEN \
  --gemini_key $GEMINI_API_KEY
```

---

## Configuration

All hyperparameters live in **`configs/config.yaml`**. No hardcoded values exist in source files.

Key sections:

```yaml
huggingface:
  dataset_name: "Dohahemdann/business-qa-analysis"
  t5_base_model: "google/flan-t5-xl"
  gemma_base_model: "unsloth/gemma-3n-E2B-it"
  ...

t5_training:
  learning_rate: 1.0e-3
  num_train_epochs: 1
  lora:
    r: 16
    lora_alpha: 32
    ...

evaluation:
  test_sample_ratio: 0.01   # Fraction of test set to evaluate on
  max_new_tokens: 128
  judge_model: "models/gemini-2.5-flash"
  ...
```

---

## Docker

### Build image

```bash
docker build -t spark2scale .
```

### Run a specific pipeline

```bash
# Set tokens
export HF_TOKEN=hf_...
export GEMINI_API_KEY=...

# T5 Training
docker compose run t5-training

# Gemma Fine-tuning
docker compose run gemma-finetuning

# TinyLlama Fine-tuning
docker compose run tinyllama-finetuning

# Evaluation
docker compose run evaluation

# MLflow UI (opens on http://localhost:5000)
docker compose up mlflow
```

> **GPU requirement:** Docker Compose is configured to pass all NVIDIA GPUs to each service. Ensure the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) is installed on your host.

---

## Running Individual Pipelines

Convenience bash scripts are provided in `scripts/`:

```bash
chmod +x scripts/*.sh

HF_TOKEN=$HF_TOKEN bash scripts/run_t5_training.sh
HF_TOKEN=$HF_TOKEN bash scripts/run_gemma_finetuning.sh
HF_TOKEN=$HF_TOKEN bash scripts/run_tinyllama_finetuning.sh
HF_TOKEN=$HF_TOKEN GEMINI_KEY=$GEMINI_API_KEY bash scripts/run_evaluation.sh
```

---

## MLflow Tracking

Gemma fine-tuning logs to MLflow automatically. To view the UI locally:

```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000
```

Then open [http://localhost:5000](http://localhost:5000).

Tracked per run:

- Hyperparameters (lr, epochs, batch size, seed)
- Training loss (every step)
- Model artifacts (LoRA weights via `mlflow.pytorch.log_model`)
- Checkpoints (as generic artifacts)

---

## Tests

```bash
# Install test dependencies
pip install pytest

# Run all tests (no GPU required)
pytest tests/ -v
```

Tests cover:

- Config loading and schema validation
- All metric functions (METEOR, G-Eval, Diversity) with edge cases

---

## Environment Variables

| Variable         | Required | Description                                            |
| ---------------- | -------- | ------------------------------------------------------ |
| `HF_TOKEN`       | Yes      | HuggingFace access token (for gated models & Hub push) |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for LLM-as-judge evaluation      |

---

## Notes on API Keys

- **Never commit `.env` to git.** It is listed in `.gitignore`.
- Rotate your `HF_TOKEN` from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) if it was previously hardcoded in a notebook.
- `GEMINI_API_KEY` is only required if you want LLM-as-judge evaluation. All other metrics run without it.

---

## License

MIT — see `LICENSE` for details.
