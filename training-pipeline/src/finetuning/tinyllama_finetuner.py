"""
src/finetuning/tinyllama_finetuner.py
──────────────────────────────────────
Fine-tuning pipeline for TinyLlama-1.1B-Chat using LoRA (causal LM).

Run:
    python -m src.finetuning.tinyllama_finetuner --config configs/config.yaml
"""

import argparse
import os

import torch
from datasets import load_dataset
from huggingface_hub import login
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainerArguments,
    TrainerCallback,
    TrainingArguments,
)

from src.utils import ensure_dir, get_logger, load_config, log_gpu_stats, set_seed

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Progress callback
# ─────────────────────────────────────────────────────────────────────────────

class ProgressCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if state.is_local_process_zero and logs:
            loss = logs.get("loss", "N/A")
            lr = logs.get("learning_rate", "N/A")
            loss_str = f"{loss:.4f}" if isinstance(loss, float) else loss
            lr_str = f"{lr:.2e}" if isinstance(lr, float) else lr
            logger.info(
                f"Step {state.global_step}/{state.max_steps} | "
                f"loss: {loss_str} | lr: {lr_str}"
            )

    def on_epoch_end(self, args, state, control, **kwargs):
        logger.info(f"Epoch {int(state.epoch)} complete")


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def load_and_tokenize_dataset(cfg: dict, tokenizer):
    dataset_name = cfg["huggingface"]["dataset_name"]
    max_length = cfg["tinyllama_finetuning"]["max_length"]

    logger.info(f"Loading dataset: {dataset_name}")
    dataset = load_dataset(dataset_name, split="train")

    def format_example(x):
        return {
            "text": (
                f"<|user|>\n{x['question']}\nContext: {x['context']}\n"
                f"<|assistant|>\n{x['answer']}</s>"
            )
        }

    dataset = dataset.map(format_example, remove_columns=dataset.column_names)

    def tokenize(x):
        enc = tokenizer(
            x["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )
        enc["labels"] = enc["input_ids"].copy()
        return enc

    tokenized = dataset.map(tokenize, remove_columns=["text"])
    return tokenized


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

def build_model_and_tokenizer(cfg: dict):
    model_id = cfg["huggingface"]["tinyllama_base_model"]
    lora_cfg = cfg["tinyllama_finetuning"]["lora"]

    logger.info(f"Loading model: {model_id}")

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.float16,
        device_map={"": 0},
    )
    model.config.use_cache = False
    model.enable_input_require_grads()

    lora_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        target_modules=lora_cfg["target_modules"],
        lora_dropout=lora_cfg["lora_dropout"],
        bias=lora_cfg["bias"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def finetune(cfg: dict, hf_token: str):
    log_gpu_stats(logger)

    t_cfg = cfg["tinyllama_finetuning"]
    output_dir = ensure_dir(t_cfg["output_dir"])
    hub_repo = cfg["huggingface"]["tinyllama_finetuned_repo"]

    model, tokenizer = build_model_and_tokenizer(cfg)
    tokenized_dataset = load_and_tokenize_dataset(cfg, tokenizer)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=t_cfg["num_train_epochs"],
        per_device_train_batch_size=t_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=t_cfg["gradient_accumulation_steps"],
        learning_rate=t_cfg["learning_rate"],
        fp16=True,
        logging_steps=t_cfg["logging_steps"],
        save_strategy="epoch",
        optim="adamw_torch_fused",
        report_to="none",
        warmup_steps=t_cfg["warmup_steps"],
        lr_scheduler_type=t_cfg["lr_scheduler_type"],
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        push_to_hub=True,
        hub_model_id=hub_repo,
        hub_token=hf_token,
        hub_strategy="every_save",
    )

    trainer = Trainer(
        model=model,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        callbacks=[ProgressCallback()],
        args=training_args,
    )

    logger.info("Starting TinyLlama fine-tuning …")
    trainer.train()

    logger.info("Pushing final model to HuggingFace Hub …")
    trainer.push_to_hub()
    tokenizer.push_to_hub(hub_repo, token=hf_token)
    logger.info(f"Done → https://huggingface.co/{hub_repo}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune TinyLlama with LoRA")
    p.add_argument("--config", default="configs/config.yaml")
    p.add_argument("--hf_token", default=os.getenv("HF_TOKEN", ""))
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    login(token=args.hf_token)
    cfg = load_config(args.config)
    finetune(cfg, args.hf_token)
