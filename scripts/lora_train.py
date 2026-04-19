#!/usr/bin/env python3
import os
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    set_seed
)
from peft import (
    LoraConfig,
    get_peft_model,
    TaskType,
    PeftModel,
    PeftConfig
)
from peft.tuners.lora import LoraLayer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.data_loader import DataLoaderFactory, DataLoaderConfig

logger = get_logger(__name__)


@dataclass
class LoRATrainingConfig:
    base_model: str = "gpt2"
    output_dir: str = "./output/lora_model"
    data_path: str = "./data/train.json"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 3e-4
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: str = "q_proj,v_proj,k_proj,o_proj,gate_proj,up_proj,down_proj"
    warmup_ratio: float = 0.03
    weight_decay: float = 0.001
    logging_steps: int = 10
    save_steps: int = 100
    eval_steps: int = 100
    max_grad_norm: float = 1.0
    seed: int = 42
    use_flash_attention: bool = False
    use_4bit: bool = False
    bf16: bool = False
    fp16: bool = False


class LoRATrainer:
    def __init__(self, config: LoRATrainingConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.device = self._get_device()

    def _get_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_tokenizer(self):
        logger.info(f"Loading tokenizer from {self.config.base_model}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.config.base_model,
            trust_remote_code=True
        )

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        if self.tokenizer.padding_side is None:
            self.tokenizer.padding_side = "left"

        logger.info(f"Tokenizer loaded: vocab_size={len(self.tokenizer)}")

    def _load_model(self):
        logger.info(f"Loading base model from {self.config.base_model}")

        load_kwargs = {
            "pretrained_model_name_or_path": self.config.base_model,
            "trust_remote_code": True,
        }

        if self.device == "cuda" and self.config.use_4bit:
            from transformers import BitsAndBytesConfig
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            load_kwargs["quantization_config"] = bnb_config
            load_kwargs["torch_dtype"] = torch.float16
        elif self.device == "cuda":
            load_kwargs["torch_dtype"] = torch.float16
        else:
            load_kwargs["torch_dtype"] = torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(**load_kwargs)

        if self.tokenizer.pad_token_id is not None:
            self.model.config.pad_token_id = self.tokenizer.pad_token_id

        logger.info(f"Model loaded on {self.device}: {sum(p.numel() for p in self.model.parameters())} parameters")

    def _apply_lora(self):
        logger.info("Applying LoRA adapters...")

        target_modules = self.config.target_modules.split(",") if self.config.target_modules else None

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=self.config.lora_rank,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            target_modules=target_modules,
            bias="none",
        )

        self.model = get_peft_model(self.model, lora_config)

        self.model.print_trainable_parameters()

        for name, module in self.model.named_modules():
            if isinstance(module, LoraLayer):
                module.to(self.device)

        logger.info("LoRA adapters applied successfully")

    def _prepare_dataset(self) -> Dataset:
        logger.info(f"Loading training data from {self.config.data_path}")

        loader_config = DataLoaderConfig(
            file_path=self.config.data_path,
            file_type="json",
            num_proc=1
        )
        loader = DataLoaderFactory.create(loader_config)
        data = loader.load()

        logger.info(f"Loaded {len(data)} training samples")

        def format_instruction(example):
            instruction = example.get("instruction", "")
            input_text = example.get("input", "")
            output = example.get("output", "")

            if input_text:
                prompt = f"Instruction: {instruction}\nInput: {input_text}\nOutput: {output}"
            else:
                prompt = f"Instruction: {instruction}\nOutput: {output}"

            return {"text": prompt}

        formatted_data = [format_instruction(item) for item in data]

        dataset = Dataset.from_list(formatted_data)

        def tokenize_function(examples):
            result = self.tokenizer(
                examples["text"],
                truncation=True,
                max_length=512,
                padding=False,
            )
            result["labels"] = result["input_ids"].copy()
            return result

        tokenized_dataset = dataset.map(
            tokenize_function,
            batched=True,
            remove_columns=dataset.column_names,
            desc="Tokenizing dataset"
        )

        return tokenized_dataset

    def _setup_training_arguments(self) -> TrainingArguments:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=self.config.num_train_epochs,
            per_device_train_batch_size=self.config.per_device_train_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            warmup_ratio=self.config.warmup_ratio,
            logging_steps=self.config.logging_steps,
            save_steps=self.config.save_steps,
            eval_steps=self.config.eval_steps,
            max_grad_norm=self.config.max_grad_norm,
            seed=self.config.seed,
            bf16=self.config.bf16 and self.device == "cuda",
            fp16=self.config.fp16 and self.device == "cuda",
            logging_dir=str(output_dir / "logs"),
            report_to="none",
            remove_unused_columns=False,
            dataloader_num_workers=0,
            group_by_length=False,
            lr_scheduler_type="cosine",
            save_total_limit=3,
        )

        return training_args

    def train(self):
        set_seed(self.config.seed)

        logger.info("=" * 60)
        logger.info("Starting LoRA Fine-tuning")
        logger.info(f"Device: {self.device}")
        logger.info(f"Base Model: {self.config.base_model}")
        logger.info(f"LoRA Rank: {self.config.lora_rank}")
        logger.info(f"Output Directory: {self.config.output_dir}")
        logger.info("=" * 60)

        self._load_tokenizer()
        self._load_model()
        self._apply_lora()

        train_dataset = self._prepare_dataset()

        data_collator = DataCollatorForSeq2Seq(
            tokenizer=self.tokenizer,
            model=self.model,
            padding=True,
            return_tensors="pt",
        )

        training_args = self._setup_training_arguments()

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            data_collator=data_collator,
            tokenizer=self.tokenizer,
        )

        trainer.train()

        logger.info("Training completed! Saving model...")
        self.save_model()

        return self.model

    def save_model(self, output_dir: Optional[str] = None):
        save_dir = output_dir or self.config.output_dir

        logger.info(f"Saving model to {save_dir}")

        self.model.save_pretrained(save_dir)
        self.tokenizer.save_pretrained(save_dir)

        adapter_config_path = Path(save_dir) / "adapter_config.json"
        if adapter_config_path.exists():
            logger.info("LoRA adapter saved successfully")

        logger.info(f"Model saved to {save_dir}")

    def merge_and_save(self, output_dir: Optional[str] = None):
        save_dir = output_dir or self.config.output_dir

        logger.info("Merging LoRA weights with base model...")

        merged_model = self.model.merge_and_unload()

        merged_save_dir = str(Path(save_dir) / "merged")
        merged_model.save_pretrained(merged_save_dir)
        self.tokenizer.save_pretrained(merged_save_dir)

        logger.info(f"Merged model saved to {merged_save_dir}")


def load_lora_config_from_json(config_path: str) -> LoRATrainingConfig:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return LoRATrainingConfig(**data)


def main():
    parser = argparse.ArgumentParser(description="LoRA Fine-tuning for Tech Blog AI")
    parser.add_argument("--config", "-c", type=str, help="Path to training config JSON")
    parser.add_argument("--model", "-m", type=str, help="Base model name or path")
    parser.add_argument("--data", "-d", type=str, help="Training data path")
    parser.add_argument("--output", "-o", type=str, help="Output directory")
    parser.add_argument("--rank", "-r", type=int, default=8, help="LoRA rank")
    parser.add_argument("--alpha", "-a", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--epochs", "-e", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", "-b", type=int, default=2, help="Per device batch size")
    parser.add_argument("--learning-rate", "-lr", type=float, default=3e-4, help="Learning rate")

    args = parser.parse_args()

    config = LoRATrainingConfig()

    if args.config and Path(args.config).exists():
        with open(args.config, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            for key, value in config_data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

    if args.model:
        config.base_model = args.model
    if args.data:
        config.data_path = args.data
    if args.output:
        config.output_dir = args.output
    if args.rank:
        config.lora_rank = args.rank
    if args.alpha:
        config.lora_alpha = args.alpha
    if args.epochs:
        config.num_train_epochs = args.epochs
    if args.batch_size:
        config.per_device_train_batch_size = args.batch_size
    if args.learning_rate:
        config.learning_rate = args.learning_rate

    trainer = LoRATrainer(config)
    trainer.train()


if __name__ == "__main__":
    main()