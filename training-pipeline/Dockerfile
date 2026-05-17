# ─────────────────────────────────────────────
# Spark2Scale – Dockerfile
# Base: NVIDIA CUDA 12.1 + cuDNN 8 + Ubuntu 22.04
# ─────────────────────────────────────────────

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# ── System deps ──────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip \
        git curl wget ca-certificates \
        libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && ln -sf python3.11 /usr/bin/python3 \
    && ln -sf python3 /usr/bin/python \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Working dir ───────────────────────────────
WORKDIR /app

# ── Python deps (layer-cached) ────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Project code ─────────────────────────────
COPY . .

# ── NLTK data ─────────────────────────────────
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('wordnet')"

# ── Environment ───────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache/huggingface \
    MLFLOW_TRACKING_URI=sqlite:///mlflow.db

# ── Expose MLflow port (optional) ─────────────
EXPOSE 5000

# ── Default command: evaluation pipeline ──────
CMD ["python", "-m", "src.evaluation.evaluator", \
     "--config", "configs/config.yaml", \
     "--models", "t5_finetuned", "t5_base"]
