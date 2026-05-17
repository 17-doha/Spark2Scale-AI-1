"""
src/utils/helpers.py
────────────────────
Shared utilities: config loading, logging, device detection, seed setting.
"""

import logging
import os
import random

import numpy as np
import torch
import yaml


# ── Logging ──────────────────────────────────────────────────────────────────

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


# ── Config ───────────────────────────────────────────────────────────────────

def load_config(path: str = "configs/config.yaml") -> dict:
    """Load the central YAML config and return as a nested dict."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ── Reproducibility ───────────────────────────────────────────────────────────

def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ── Device ───────────────────────────────────────────────────────────────────

def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def log_gpu_stats(logger: logging.Logger) -> None:
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        reserved = round(torch.cuda.max_memory_reserved() / 1024 ** 3, 3)
        total = round(props.total_memory / 1024 ** 3, 3)
        logger.info(f"GPU: {props.name} | Total: {total} GB | Reserved: {reserved} GB")
    else:
        logger.info("Running on CPU")


# ── Output dirs ───────────────────────────────────────────────────────────────

def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
