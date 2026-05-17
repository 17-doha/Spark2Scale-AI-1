"""
src/training/t5_trainer.py
──────────────────────────
Full fine-tuning pipeline for FLAN-T5-XL with LoRA + QLoRA (4-bit).

Run:
    python -m src.training.t5_trainer --config configs/config.yaml
"""

import argparse
import os

import torch
from datasets import load_dataset
from huggingface_hub import HfApi, login
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainingArguments,
    T5Config,
    T5ForConditionalGeneration,
    Trainer,
    TrainerCallback,
)

from src.utils import ensure_dir, get_logger, load_config, log_gpu_stats, set_seed

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Custom model: T5 with RoPE support
# ─────────────────────────────────────────────────────────────────────────────

class RopeT5ForConditionalGeneration(T5ForConditionalGeneration):
    """Thin wrapper that preserves RoPE-modified config keys loaded from checkpoint."""

    def __init__(self, config: T5Config):
        super().__init__(config)


# ─────────────────────────────────────────────────────────────────────────────
# HuggingFace Hub callback – upload each checkpoint automatically
# ─────────────────────────────────────────────────────────────────────────────

class PushToHubCallback(TrainerCallback):
    def __init__(self, output_dir: str, hub_model_id: str):
        self.output_dir = output_dir
        self.hub_model_id = hub_model_id
        self.api = HfApi()

    def on_save(self, args, state, control, **kwargs):
        checkpoint_dir = os.path.join(self.output_dir, f"checkpoint-{state.global_step}")
        self.api.upload_folder(
            folder_path=checkpoint_dir,
            repo_id=self.hub_model_id,
            repo_type="model",
            path_in_repo=f"checkpoint-{state.global_step}",
            commit_message=f"Checkpoint at step {state.global_step}",
        )
        logger.info(f"Uploaded checkpoint-{state.global_step} to Hub ({self.hub_model_id})")


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def load_data(cfg: dict):
    dataset_name = cfg["huggingface"]["dataset_name"]
    logger.info(f"Loading dataset: {dataset_name}")
    ds = load_dataset(dataset_name)
    return ds["train"], ds["test"]


def build_preprocess_fn(tokenizer, cfg: dict):
    max_input = cfg["t5_training"]["max_input_length"]
    max_target = cfg["t5_training"]["max_target_length"]

    def preprocess_function(examples):
        inputs = [
            f"Q: {q} Context: {c}"
            for q, c in zip(examples["question"], examples["context"])
        ]
        targets = examples["answer"]

        model_inputs = tokenizer(
            inputs,
            max_length=max_input,
            truncation=True,
            padding=False,
            add_special_tokens=True,
        )
        labels = tokenizer(
            text_target=targets,
            max_length=max_target,
            truncation=True,
            padding=False,
        )
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    return preprocess_function


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

def build_model(cfg: dict):
    model_id = cfg["huggingface"]["t5_finetuned_repo"]
    lora_cfg = cfg["t5_training"]["lora"]

    logger.info(f"Loading base model: {model_id}")

    quant_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    config = T5Config.from_pretrained(model_id)
    logger.info(f"Model num_heads: {config.num_heads}")

    model = RopeT5ForConditionalGeneration.from_pretrained(
        model_id,
        quantization_config=quant_cfg,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg["lora_dropout"],
        target_modules=lora_cfg["target_modules"],
        bias=lora_cfg["bias"],
    )
    model = get_peft_model(model, lora_config)
    model.config.use_cache = False
    model.print_trainable_parameters()

    return model


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def train(cfg: dict, hf_token: str):
    set_seed(42)
    log_gpu_stats(logger)

    t5_cfg = cfg["t5_training"]
    output_dir = ensure_dir(t5_cfg["output_dir"])
    hub_repo = cfg["huggingface"]["t5_checkpoint_repo"]

    # Tokenizer
    model_id = cfg["huggingface"]["t5_finetuned_repo"]
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.pad_token = tokenizer.eos_token

    # Data
    train_ds, test_ds = load_data(cfg)
    preprocess_fn = build_preprocess_fn(tokenizer, cfg)
    tokenized_train = train_ds.map(
        preprocess_fn, batched=True, batch_size=16,
        remove_columns=train_ds.column_names, desc="Tokenising train",
    )
    tokenized_test = test_ds.map(
        preprocess_fn, batched=True, batch_size=16,
        remove_columns=test_ds.column_names, desc="Tokenising test",
    )

    # Model
    model = build_model(cfg)

    # Trainer
    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=t5_cfg["num_train_epochs"],
        per_device_train_batch_size=t5_cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=t5_cfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=t5_cfg["gradient_accumulation_steps"],
        learning_rate=t5_cfg["learning_rate"],
        warmup_ratio=t5_cfg["warmup_ratio"],
        weight_decay=t5_cfg["weight_decay"],
        eval_steps=t5_cfg["eval_steps"],
        eval_strategy="steps",
        save_strategy="steps",
        save_steps=t5_cfg["save_steps"],
        logging_steps=t5_cfg["logging_steps"],
        fp16=False,
        bf16=True,
        optim="paged_adamw_8bit",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": True},
        dataloader_num_workers=2,
        remove_unused_columns=True,
        predict_with_generate=False,
        dataloader_pin_memory=True,
        dataloader_prefetch_factor=2,
        push_to_hub=False,
        report_to="tensorboard",
        logging_dir=os.path.join(output_dir, "logs"),
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        max_length=t5_cfg["max_input_length"],
        return_tensors="pt",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_test,
        data_collator=data_collator,
        callbacks=[PushToHubCallback(output_dir=output_dir, hub_model_id=hub_repo)],
        tokenizer=tokenizer,
    )

    logger.info("Starting T5 training …")
    train_result = trainer.train()
    trainer.push_to_hub()

    metrics = train_result.metrics
    logger.info(f"Training done in {metrics.get('train_runtime', 'N/A'):.1f}s "
                f"| loss: {metrics.get('train_loss', 'N/A'):.4f}")

    eval_result = trainer.evaluate()
    logger.info(f"Eval loss: {eval_result.get('eval_loss', 'N/A'):.4f}")

    return train_result, eval_result


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Train FLAN-T5-XL with LoRA")
    p.add_argument("--config", default="configs/config.yaml")
    p.add_argument("--hf_token", default=os.getenv("HF_TOKEN", ""))
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    login(token=args.hf_token)
    cfg = load_config(args.config)
    train(cfg, args.hf_token)
