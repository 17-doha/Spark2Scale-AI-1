"""
src/evaluation/evaluator.py
─────────────────────────────
Unified evaluation pipeline for all three models (T5, Gemma, TinyLlama).
Computes latency, quality, faithfulness, METEOR, G-Eval, diversity,
semantic similarity, and optional Gemini LLM-as-judge scores.

Run:
    python -m src.evaluation.evaluator \\
        --config configs/config.yaml \\
        --models t5_finetuned t5_base \\
        --gemini_key <YOUR_KEY>
"""

import argparse
import gc
import json
import os
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from datasets import load_dataset
from huggingface_hub import login, snapshot_download
from peft import PeftConfig, PeftModel
from tqdm import tqdm
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    T5ForConditionalGeneration,
)

from src.evaluation.llm_judge import GeminiJudge
from src.evaluation.metrics import (
    compute_diversity_metrics,
    compute_faithfulness,
    compute_g_eval,
    compute_meteor,
    compute_semantic_similarity,
    get_latency_metrics,
    get_quality_metrics,
)
from src.utils import ensure_dir, get_logger, load_config, set_seed

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────

def load_test_subset(cfg: dict):
    ev_cfg = cfg["evaluation"]
    ds = load_dataset(cfg["huggingface"]["dataset_name"], split="test")
    ds = ds.shuffle(seed=ev_cfg["seed"])
    n = max(1, int(len(ds) * ev_cfg["test_sample_ratio"]))
    subset = ds.select(range(n))
    logger.info(f"Evaluation subset: {n}/{len(ds)} samples")
    return list(subset)


# ─────────────────────────────────────────────────────────────────────────────
# Model loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_t5_finetuned(cfg: dict):
    repo_id = cfg["huggingface"]["t5_checkpoint_repo"]
    checkpoint = cfg["huggingface"]["t5_checkpoint_folder"]
    local_path = snapshot_download(
        repo_id=repo_id,
        allow_patterns=[f"{checkpoint}/*"],
        local_dir="./outputs/t5_downloaded",
        local_dir_use_symlinks=False,
    )
    ckpt_path = os.path.join(local_path, checkpoint)
    logger.info(f"T5 fine-tuned checkpoint: {ckpt_path}")

    tokenizer = AutoTokenizer.from_pretrained(ckpt_path)
    tokenizer.pad_token = tokenizer.eos_token

    model = T5ForConditionalGeneration.from_pretrained(
        ckpt_path, device_map="auto", torch_dtype=torch.bfloat16
    )
    model.eval()
    return model, tokenizer


def load_t5_base(cfg: dict):
    model_id = cfg["huggingface"]["t5_base_model"]
    logger.info(f"Loading T5 base: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    quant = BitsAndBytesConfig(load_in_8bit=True)
    model = T5ForConditionalGeneration.from_pretrained(
        model_id, device_map="auto", quantization_config=quant
    )
    model.eval()
    return model, tokenizer


# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_responses(data: List[dict], model, tokenizer, max_length: int = 150, batch_size: int = 8) -> List[str]:
    inputs_text = [
        f"question: {item['question']} context: {item['context']}"
        for item in data
    ]
    generated = []

    for i in range(0, len(inputs_text), batch_size):
        batch = inputs_text[i : i + batch_size]
        enc = tokenizer(
            batch, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(model.device)

        with torch.no_grad():
            out = model.generate(
                input_ids=enc.input_ids,
                attention_mask=enc.attention_mask,
                max_length=max_length,
                do_sample=True,
                top_k=50,
                top_p=0.95,
                pad_token_id=tokenizer.eos_token_id,
            )
        generated.extend(tokenizer.batch_decode(out, skip_special_tokens=True))

    return generated


# ─────────────────────────────────────────────────────────────────────────────
# Core per-model evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_model(
    model,
    tokenizer,
    test_data: List[dict],
    model_name: str,
    ev_cfg: dict,
) -> Dict:
    results = []

    for item in tqdm(test_data, desc=f"Evaluating {model_name}"):
        input_text = item.get("instruction", item.get("question", ""))
        target_text = item.get("response", item.get("output", item.get("answer", "")))
        context = item.get("context", input_text)

        if not input_text:
            continue

        # Generate
        enc = tokenizer(input_text, return_tensors="pt", max_length=512, truncation=True).to(model.device)
        with torch.no_grad():
            out = model.generate(
                enc.input_ids,
                max_new_tokens=ev_cfg["max_new_tokens"],
                do_sample=False,
                num_beams=1,
                pad_token_id=tokenizer.eos_token_id,
            )
        generated = tokenizer.decode(out[0], skip_special_tokens=True)

        faith = compute_faithfulness(
            generated, context,
            top_k=ev_cfg["top_k_chunks"],
            entailment_threshold=ev_cfg["entailment_threshold"],
            contradiction_threshold=ev_cfg["contradiction_threshold"],
        )
        results.append({
            "model": model_name,
            "input": input_text,
            "generated": generated,
            "reference": target_text,
            "Faithfulness": faith["faithfulness"],
            "Hallucination Rate": faith["hallucination_rate"],
            "Num Claims": faith["num_claims"],
            "Num Supported": faith["num_supported"],
            "METEOR": compute_meteor(generated, target_text),
            "G-Eval": compute_g_eval(generated, context),
            "Semantic Similarity": compute_semantic_similarity(generated, target_text),
        })

    df = pd.DataFrame(results)
    summary = df.drop(columns=["input", "generated", "reference"], errors="ignore").mean(numeric_only=True).to_dict()
    summary["model"] = model_name
    return summary, df


# ─────────────────────────────────────────────────────────────────────────────
# Latency / perplexity pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_latency_quality_pipeline(test_data: List[dict], models: dict) -> pd.DataFrame:
    records = []
    for model_name, (model, tokenizer) in models.items():
        logger.info(f"Latency/quality eval: {model_name}")
        for item in tqdm(test_data):
            inp = item.get("instruction", item.get("question", ""))
            tgt = item.get("response", item.get("output", item.get("answer", "")))
            if not inp:
                continue
            lat = get_latency_metrics(model, tokenizer, inp)
            qual = get_quality_metrics(model, tokenizer, inp, tgt)
            records.append({"model": model_name, **lat, **qual})
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# Diversity pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_diversity_pipeline(test_data: List[dict], model, tokenizer, model_name: str, ref_col: str = "answer") -> pd.DataFrame:
    generated = generate_responses(test_data, model, tokenizer)
    references = [item.get(ref_col, "") for item in test_data]

    rows = []
    for gen in generated:
        d2, rr = compute_diversity_metrics([gen], n=2)
        rows.append({"generated": gen, "distinct_2": d2, "repetition_rate": rr})

    df = pd.DataFrame(rows)
    df["reference"] = references
    df["model"] = model_name
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Gemini judge pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_gemini_judge(
    df: pd.DataFrame,
    judge: GeminiJudge,
    model_label: str,
    pause_s: float = 2.0,
) -> pd.DataFrame:
    scores, decisions, summaries, analyses = [], [], [], []

    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"Gemini judge: {model_label}"):
        result = judge.evaluate(
            question=row.get("question", row.get("input", "")),
            context=row.get("context", ""),
            generated_response=row.get("generated", ""),
        )
        if "error" in result:
            scores.append(np.nan)
            decisions.append(result["error"])
            summaries.append("")
            analyses.append("{}")
        else:
            scores.append(result.get("score", np.nan))
            decisions.append(result.get("final_decision", ""))
            summaries.append(result.get("executive_summary", ""))
            analyses.append(json.dumps(result))
        time.sleep(pause_s)

    df = df.copy()
    df[f"{model_label}_gemini_score"] = scores
    df[f"{model_label}_gemini_decision"] = decisions
    df[f"{model_label}_gemini_summary"] = summaries
    df[f"{model_label}_gemini_analysis"] = analyses
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Plotting
# ─────────────────────────────────────────────────────────────────────────────

def plot_metric_comparison(all_results: dict, metrics: List[str], output_dir: str):
    model_names = list(all_results.keys())
    colors = sns.color_palette("viridis", len(model_names))

    for metric in metrics:
        fig, ax = plt.subplots(figsize=(8, 6))
        scores = [all_results[m].get(metric, 0) for m in model_names]
        bars = ax.bar(model_names, scores, color=colors, alpha=0.85, edgecolor="black", linewidth=1.2)

        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h:.3f}", ha="center", va="bottom", fontweight="bold")

        ax.set_title(f"{metric} – Model Comparison", fontsize=14, fontweight="bold")
        ax.set_ylabel(metric)
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        plt.tight_layout()
        path = os.path.join(output_dir, f"{metric.replace(' ', '_').replace('/', '_')}.png")
        plt.savefig(path)
        plt.close()
        logger.info(f"Saved plot: {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_evaluation(cfg: dict, model_keys: List[str], gemini_key: Optional[str] = None):
    import time as _time

    ev_cfg = cfg["evaluation"]
    output_dir = ensure_dir(ev_cfg["output_dir"])
    set_seed(ev_cfg["seed"])

    test_data = load_test_subset(cfg)

    # Build model registry
    model_registry = {
        "t5_finetuned": load_t5_finetuned,
        "t5_base": load_t5_base,
    }

    models_to_eval = {}
    for key in model_keys:
        if key not in model_registry:
            logger.warning(f"Unknown model key: {key} – skipping")
            continue
        models_to_eval[key] = model_registry[key](cfg)

    all_summaries = {}
    all_dfs = []

    for model_name, (model, tokenizer) in models_to_eval.items():
        summary, df = evaluate_model(model, tokenizer, test_data, model_name, ev_cfg)
        all_summaries[model_name] = summary
        all_dfs.append(df)

        del model
        gc.collect()
        torch.cuda.empty_cache()

    # Latency / quality (re-load models sequentially)
    lat_models = {}
    for key in model_keys:
        if key in model_registry:
            lat_models[key] = model_registry[key](cfg)

    lat_df = run_latency_quality_pipeline(test_data, lat_models)
    lat_df.to_csv(os.path.join(output_dir, "latency_quality.csv"), index=False)

    for model, (m, _) in lat_models.items():
        del m
    gc.collect()
    torch.cuda.empty_cache()

    # Comparison table
    comparison_df = pd.DataFrame(all_summaries).T
    comparison_df.to_csv(os.path.join(output_dir, "model_comparison.csv"))
    logger.info(f"\n{comparison_df.to_string()}")

    # Plots
    plot_metrics = ["Faithfulness", "Hallucination Rate", "METEOR", "G-Eval", "Semantic Similarity"]
    plot_metric_comparison(all_summaries, plot_metrics, output_dir)

    # Optional Gemini judge
    if gemini_key and all_dfs:
        judge = GeminiJudge(model_name=ev_cfg["judge_model"], api_key=gemini_key)
        judged_dfs = []
        for df in all_dfs:
            model_label = df["model"].iloc[0].replace(" ", "_")
            judged = run_gemini_judge(df.head(5), judge, model_label)
            judged_dfs.append(judged)
            judged.to_csv(os.path.join(output_dir, f"gemini_judge_{model_label}.csv"), index=False)

    logger.info("Evaluation complete.")
    return all_summaries


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Spark2Scale Evaluation Pipeline")
    p.add_argument("--config", default="configs/config.yaml")
    p.add_argument("--models", nargs="+", default=["t5_finetuned", "t5_base"],
                   help="Models to evaluate: t5_finetuned, t5_base")
    p.add_argument("--hf_token", default=os.getenv("HF_TOKEN", ""))
    p.add_argument("--gemini_key", default=os.getenv("GEMINI_API_KEY", ""))
    return p.parse_args()


if __name__ == "__main__":
    import time
    args = parse_args()
    if args.hf_token:
        login(token=args.hf_token)
    cfg = load_config(args.config)
    run_evaluation(cfg, args.models, gemini_key=args.gemini_key or None)
