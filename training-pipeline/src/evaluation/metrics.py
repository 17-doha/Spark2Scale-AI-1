"""
src/evaluation/metrics.py
─────────────────────────
All evaluation metrics used across Spark2Scale models:
  - Latency / throughput
  - Cross-entropy loss / perplexity
  - METEOR
  - Semantic similarity (sentence-transformers)
  - RAGAS-style faithfulness (NLI claim-level)
  - G-Eval (heuristic)
  - Diversity (Distinct-N, repetition rate)
"""

import re
import time
from collections import Counter
from threading import Thread
from typing import Dict, List, Optional

import nltk
import numpy as np
import torch
from nltk import word_tokenize
from nltk.translate.meteor_score import meteor_score
from nltk.util import ngrams
from sentence_transformers import SentenceTransformer, util as st_util
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    TextIteratorStreamer,
)

nltk.download("punkt", quiet=True)
nltk.download("wordnet", quiet=True)


# ─────────────────────────────────────────────────────────────────────────────
# Lazy-loaded shared models
# ─────────────────────────────────────────────────────────────────────────────

_embedding_model: Optional[SentenceTransformer] = None
_nli_model = None
_nli_tokenizer = None


def _get_embedding_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _embedding_model = SentenceTransformer(model_name, device=device)
    return _embedding_model


def _get_nli_model(model_name: str = "roberta-large-mnli"):
    global _nli_model, _nli_tokenizer
    if _nli_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _nli_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _nli_model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
    return _nli_model, _nli_tokenizer


# ─────────────────────────────────────────────────────────────────────────────
# Latency & throughput
# ─────────────────────────────────────────────────────────────────────────────

def get_latency_metrics(model, tokenizer, input_text: str, max_tokens: int = 128) -> Dict:
    """TTFT, TPOT, Throughput, Total Latency for any seq2seq model."""
    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    streamer = TextIteratorStreamer(tokenizer, skip_special_tokens=True)
    generation_kwargs = dict(**inputs, streamer=streamer, max_new_tokens=max_tokens, do_sample=False)

    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    start_time = time.time()
    thread.start()

    generated_text = ""
    ttft = 0.0

    for i, chunk in enumerate(streamer):
        if i == 0:
            ttft = time.time() - start_time
        generated_text += chunk

    end_time = time.time()
    thread.join()

    total_latency = end_time - start_time
    output_tokens = len(tokenizer.encode(generated_text))
    tpot = (total_latency - ttft) / max(output_tokens - 1, 1)
    throughput = output_tokens / total_latency if total_latency > 0 else 0

    return {
        "TTFT (s)": ttft,
        "Total Latency (s)": total_latency,
        "TPOT (s/token)": tpot,
        "Throughput (tok/s)": throughput,
        "Output Length": output_tokens,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cross-entropy loss & perplexity
# ─────────────────────────────────────────────────────────────────────────────

def get_quality_metrics(model, tokenizer, input_text: str, target_text: str) -> Dict:
    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    target_inputs = tokenizer(target_text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model(input_ids=inputs.input_ids, labels=target_inputs.input_ids)
        loss = outputs.loss.item()

    return {
        "Cross-Entropy Loss": loss,
        "Perplexity": torch.exp(torch.tensor(loss)).item(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# METEOR
# ─────────────────────────────────────────────────────────────────────────────

def compute_meteor(generated: str, reference: str) -> float:
    try:
        return meteor_score(
            [word_tokenize(reference.lower())],
            word_tokenize(generated.lower()),
        )
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Semantic similarity
# ─────────────────────────────────────────────────────────────────────────────

def compute_semantic_similarity(generated: str, reference: str, model_name: str = "all-MiniLM-L6-v2") -> float:
    embed_model = _get_embedding_model(model_name)
    embs = embed_model.encode([generated, reference], convert_to_tensor=True)
    return st_util.cos_sim(embs[0], embs[1]).item()


# ─────────────────────────────────────────────────────────────────────────────
# NLI helper
# ─────────────────────────────────────────────────────────────────────────────

def _nli_entailment_probs(premise: str, hypothesis: str, nli_model_name: str = "roberta-large-mnli") -> Dict:
    model, tokenizer = _get_nli_model(nli_model_name)
    device = next(model.parameters()).device
    encoded = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True).to(device)
    with torch.no_grad():
        logits = model(**encoded).logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
    # roberta-large-mnli: 0=CONTRADICTION, 1=NEUTRAL, 2=ENTAILMENT
    return {"entailment": float(probs[2]), "neutral": float(probs[1]), "contradiction": float(probs[0])}


# ─────────────────────────────────────────────────────────────────────────────
# RAGAS-style faithfulness
# ─────────────────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _chunk_context(context: str, max_sentences: int = 6) -> List[str]:
    sents = _split_sentences(context)
    return [" ".join(sents[i : i + max_sentences]) for i in range(0, len(sents), max_sentences)] or [context]


def _extract_claims(text: str) -> List[str]:
    return [s for s in _split_sentences(text) if len(re.findall(r"\w+", s)) >= 4 and not s.endswith("?")]


def compute_faithfulness(
    generated: str,
    context: str,
    top_k: int = 3,
    entailment_threshold: float = 0.65,
    contradiction_threshold: float = 0.5,
) -> Dict:
    if not generated or not context:
        return {"faithfulness": 0.0, "hallucination_rate": 1.0, "num_claims": 0, "num_supported": 0, "num_contradicted": 0}

    claims = _extract_claims(generated)
    if not claims:
        return {"faithfulness": 0.0, "hallucination_rate": 1.0, "num_claims": 0, "num_supported": 0, "num_contradicted": 0}

    embed_model = _get_embedding_model()
    chunks = _chunk_context(context)
    chunk_embs = embed_model.encode(chunks, convert_to_tensor=True)

    results = []
    for claim in claims:
        claim_emb = embed_model.encode(claim, convert_to_tensor=True)
        sims = st_util.cos_sim(claim_emb, chunk_embs).cpu().numpy()[0]
        top_idx = np.argsort(-sims)[:top_k]

        per_chunk = []
        for idx in top_idx:
            nli = _nli_entailment_probs(chunks[int(idx)], claim)
            per_chunk.append(nli)

        supported = any(r["entailment"] >= entailment_threshold for r in per_chunk)
        contradicted = any(r["contradiction"] >= contradiction_threshold for r in per_chunk)
        max_entail = max(r["entailment"] for r in per_chunk)

        results.append({"supported": supported, "contradicted": contradicted, "max_entailment": max_entail})

    n = len(results)
    n_supported = sum(1 for r in results if r["supported"])
    n_contradicted = sum(1 for r in results if r["contradicted"])
    avg_entail = sum(r["max_entailment"] for r in results) / n

    faithfulness = max(0.0, min(1.0, 0.5 * avg_entail + 0.4 * (n_supported / n) - 0.1 * (n_contradicted / n)))

    return {
        "faithfulness": faithfulness,
        "hallucination_rate": 1.0 - faithfulness,
        "num_claims": n,
        "num_supported": n_supported,
        "num_contradicted": n_contradicted,
        "avg_max_entailment": avg_entail,
    }


# ─────────────────────────────────────────────────────────────────────────────
# G-Eval (heuristic prompt-guided score)
# ─────────────────────────────────────────────────────────────────────────────

def compute_g_eval(generated: str, context: str) -> float:
    if not generated:
        return 0.0

    score = 0.0
    word_count = len(generated.split())

    if 10 <= word_count <= 150:
        score += 0.3
    elif word_count > 5:
        score += 0.15

    if re.search(r"[.!?]", generated):
        score += 0.2

    if context:
        gen_words = set(generated.lower().split())
        ctx_words = set(context.lower().split())
        overlap = len(gen_words & ctx_words) / len(gen_words) if gen_words else 0
        score += 0.3 * overlap

    words = generated.split()
    if words:
        score += 0.2 * (len(set(words)) / len(words))

    return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Diversity: Distinct-N and repetition rate
# ─────────────────────────────────────────────────────────────────────────────

def compute_diversity_metrics(text_list: List[str], n: int = 2):
    all_tokens = [tok for text in text_list for tok in re.findall(r"\b\w+\b", text.lower())]
    all_ngrams = list(ngrams(all_tokens, n))
    total = len(all_ngrams)

    if total == 0:
        return 0.0, 0.0

    distinct_n = len(set(all_ngrams)) / total
    return distinct_n, 1.0 - distinct_n  # (distinct_n_score, repetition_rate)
