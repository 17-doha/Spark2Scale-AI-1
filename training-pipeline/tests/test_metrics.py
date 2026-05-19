"""
tests/test_metrics.py
──────────────────────
Smoke-tests for all metric functions (no GPU required).
"""

import pytest

from src.evaluation.metrics import (
    compute_diversity_metrics,
    compute_g_eval,
    compute_meteor,
)


def test_meteor_identical():
    score = compute_meteor("the cat sat on the mat", "the cat sat on the mat")
    assert score > 0.9


def test_meteor_different():
    score = compute_meteor("apples and oranges", "the cat sat on the mat")
    assert score < 0.5


def test_g_eval_returns_float():
    score = compute_g_eval(
        generated="Revenue increased by 15% due to new product launches.",
        context="The company launched three new products in Q3.",
    )
    assert 0.0 <= score <= 1.0


def test_g_eval_empty():
    score = compute_g_eval("", "some context")
    assert score == 0.0


def test_diversity_metrics_basic():
    texts = ["the cat sat on the mat", "the dog ran in the park"]
    distinct, repetition = compute_diversity_metrics(texts, n=2)
    assert 0.0 <= distinct <= 1.0
    assert 0.0 <= repetition <= 1.0
    assert abs(distinct + repetition - 1.0) < 1e-6


def test_diversity_metrics_empty():
    distinct, repetition = compute_diversity_metrics([], n=2)
    assert distinct == 0.0 and repetition == 0.0
