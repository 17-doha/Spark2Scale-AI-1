"""
src/finetuning/gemma_finetuner.py
──────────────────────────────────
Fine-tuning pipeline for Gemma-3n-E2B-it using Unsloth + LoRA + MLflow.

Run:
    python -m src.finetuning.gemma_finetuner --config configs/config.yaml
"""

import argparse
import json
import os

import mlflow
import torch
from datasets import load_dataset
from huggingface_hub import login
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template, standardize_data_formats, train_on_responses_only
from trl import SFTConfig, SFTTrainer

from src.utils import ensure_dir, get_logger, load_config, log_gpu_stats, set_seed

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def load_and_format_dataset(cfg: dict, tokenizer):
    dataset_name = cfg["huggingface"]["instruct_dataset"]
    logger.info(f"Loading dataset: {dataset_name}")

    dataset = load_dataset(dataset_name, split="train")
    dataset = standardize_data_formats(dataset)

    def formatting_prompts_func(examples):
        texts = []
        for instruction, context, output in zip(
            examples["question"], examples["context"], examples["answer"]
        ):
            text = (
                f"<start_of_turn>user\nContext: {context}\n\nQuestion: {instruction}<end_of_turn>\n"
                f"<start_of_turn>model\n{output}<end_of_turn>"
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True)
    logger.info(f"Dataset sample[0] text preview:\n{dataset[0]['text'][:300]}")
    return dataset


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

def build_model_and_tokenizer(cfg: dict, hf_token: str):
    g_cfg = cfg["gemma_finetuning"]
    lora_cfg = g_cfg["lora"]
    model_name = cfg["huggingface"]["gemma_base_model"]

    logger.info(f"Loading base model: {model_name}")
    os.environ["UNSLOTH_USE_MODELSCOPE"] = "1"

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=g_cfg["max_seq_length"],
        load_in_4bit=g_cfg["load_in_4bit"],
        load_in_8bit=False,
        full_finetuning=False,
        token=hf_token,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        finetune_vision_layers=lora_cfg["finetune_vision_layers"],
        finetune_language_layers=lora_cfg["finetune_language_layers"],
        finetune_attention_modules=lora_cfg["finetune_attention_modules"],
        finetune_mlp_modules=lora_cfg["finetune_mlp_modules"],
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg["lora_dropout"],
        bias=lora_cfg["bias"],
        random_state=g_cfg["seed"],
    )

    tokenizer = get_chat_template(tokenizer, chat_template="gemma-3")
    return model, tokenizer


# ─────────────────────────────────────────────────────────────────────────────
# Inference helper (used for quick post-training validation)
# ─────────────────────────────────────────────────────────────────────────────

def run_inference(model, tokenizer, question: str, context: str, max_new_tokens: int = 512) -> str:
    strict_instruction = "\n\nOutput only valid JSON. Do not include any preamble, explanation, or markdown code blocks."
    user_prompt = f"Context: {context}\n\nQuestion: {question}{strict_instruction}"

    messages = [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}]
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_tensors="pt",
        return_dict=True,
    ).to("cuda")

    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        use_cache=True,
        temperature=0,
        do_sample=False,
    )
    decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
    raw = decoded[0].split("model\n")[-1].strip()
    return raw.replace("```json", "").replace("```", "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def finetune(cfg: dict, hf_token: str):
    set_seed(cfg["gemma_finetuning"]["seed"])
    log_gpu_stats(logger)

    g_cfg = cfg["gemma_finetuning"]
    output_dir = ensure_dir(g_cfg["output_dir"])

    model, tokenizer = build_model_and_tokenizer(cfg, hf_token)
    dataset = load_and_format_dataset(cfg, tokenizer)

    hparams = {
        "learning_rate": g_cfg["learning_rate"],
        "num_train_epochs": g_cfg["num_train_epochs"],
        "batch_size": g_cfg["per_device_train_batch_size"],
        "optim": "adamw_8bit",
        "seed": g_cfg["seed"],
    }

    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment(g_cfg["mlflow_experiment"])

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=hparams["batch_size"],
            gradient_accumulation_steps=g_cfg["gradient_accumulation_steps"],
            warmup_steps=g_cfg["warmup_steps"],
            num_train_epochs=hparams["num_train_epochs"],
            learning_rate=hparams["learning_rate"],
            logging_steps=1,
            optim=hparams["optim"],
            weight_decay=g_cfg["weight_decay"],
            lr_scheduler_type="linear",
            seed=hparams["seed"],
            report_to="mlflow",
            output_dir=output_dir,
        ),
    )

    trainer = train_on_responses_only(
        trainer,
        instruction_part="<start_of_turn>user\n",
        response_part="<start_of_turn>model\n",
    )

    with mlflow.start_run(run_name="Gemma3_SFT_Spark2Scale"):
        mlflow.log_params(hparams)
        mlflow.set_tag("project", "Spark2Scale-Gemma3n")

        logger.info("Starting Gemma3n fine-tuning …")
        trainer_stats = trainer.train()

        mlflow.pytorch.log_model(
            pytorch_model=model,
            artifact_path="gemma3_model_flavor",
            pip_requirements=["unsloth", "transformers", "trl", "torch"],
        )
        mlflow.log_artifacts(output_dir, artifact_path="checkpoints")

    logger.info(f"Training finished in {trainer_stats.metrics['train_runtime']:.1f}s")

    # Save locally and push to Hub
    save_name = cfg["huggingface"]["gemma_finetuned_repo"].split("/")[-1]
    model.save_pretrained(save_name)
    tokenizer.save_pretrained(save_name)
    model.push_to_hub(cfg["huggingface"]["gemma_finetuned_repo"], token=hf_token)
    tokenizer.push_to_hub(cfg["huggingface"]["gemma_finetuned_repo"], token=hf_token)
    logger.info(f"Model pushed to {cfg['huggingface']['gemma_finetuned_repo']}")

    return trainer_stats


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune Gemma-3n with LoRA + MLflow")
    p.add_argument("--config", default="configs/config.yaml")
    p.add_argument("--hf_token", default=os.getenv("HF_TOKEN", ""))
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    login(token=args.hf_token)
    cfg = load_config(args.config)
    finetune(cfg, args.hf_token)
