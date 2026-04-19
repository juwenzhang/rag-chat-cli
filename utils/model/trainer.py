from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LRScheduler
from transformers import (
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    PreTrainedTokenizer
)
from datasets import Dataset as HFDataset
import logging
from pathlib import Path
from tqdm import tqdm
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TrainerConfig:
    output_dir: str = "./output"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 4
    learning_rate: float = 5e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    logging_dir: Optional[str] = None
    save_total_limit: int = 3
    save_steps: int = 100
    eval_steps: int = 100
    logging_steps: int = 10
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    fp16: bool = False
    bf16: bool = False
    dataloader_num_workers: int = 0
    remove_unused_columns: bool = False
    optim: str = "adamw_torch"
    report_to: str = "none"


class CustomTrainer:
    def __init__(
        self,
        model: nn.Module,
        tokenizer: PreTrainedTokenizer,
        config: TrainerConfig,
        train_dataset: Optional[HFDataset] = None,
        eval_dataset: Optional[HFDataset] = None,
        data_collator: Optional[DataCollatorForSeq2Seq] = None
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.train_dataset = train_dataset
        self.eval_dataset = eval_dataset
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.data_collator = data_collator or DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            padding=True,
            return_tensors="pt"
        )

        self.training_args = self._build_training_arguments()

    def _build_training_arguments(self) -> TrainingArguments:
        args = TrainingArguments(
            output_dir=self.config.output_dir,
            num_train_epochs=self.config.num_train_epochs,
            per_device_train_batch_size=self.config.per_device_train_batch_size,
            per_device_eval_batch_size=self.config.per_device_eval_batch_size,
            learning_rate=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            warmup_ratio=self.config.warmup_ratio,
            logging_dir=self.config.logging_dir,
            save_total_limit=self.config.save_total_limit,
            save_steps=self.config.save_steps,
            eval_steps=self.config.eval_steps,
            logging_steps=self.config.logging_steps,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            max_grad_norm=self.config.max_grad_norm,
            fp16=self.config.fp16,
            bf16=self.config.bf16,
            dataloader_num_workers=self.config.dataloader_num_workers,
            remove_unused_columns=self.config.remove_unused_columns,
            optim=self.config.optim,
            report_to=self.config.report_to,
        )
        return args

    def _preprocess_function(self, examples):
        max_length = self.tokenizer.model_max_length

        targets = examples["output"]
        inputs = [
            f"Instruction: {instr}\nInput: {inp}\nOutput:"
            for instr, inp in zip(examples["instruction"], examples["input"])
        ]

        model_inputs = self.tokenizer(
            inputs,
            max_length=max_length,
            truncation=True,
            padding="max_length"
        )

        labels = self.tokenizer(
            targets,
            max_length=max_length,
            truncation=True,
            padding="max_length"
        )

        model_inputs["labels"] = labels["input_ids"]
        model_inputs["labels"] = [
            [-100 if label == self.tokenizer.pad_token_id else label for label in labels]
            for labels in model_inputs["labels"]
        ]

        return model_inputs

    def train(self):
        logger.info("Starting training...")

        trainer = Trainer(
            model=self.model,
            args=self.training_args,
            train_dataset=self.train_dataset,
            eval_dataset=self.eval_dataset,
            data_collator=self.data_collator,
            tokenizer=self.tokenizer,
        )

        if self.train_dataset is not None:
            processed_train = self.train_dataset.map(
                self._preprocess_function,
                batched=True,
                remove_columns=self.train_dataset.column_names,
                desc="Processing training data"
            )
            trainer.train_dataset = processed_train

        if self.eval_dataset is not None:
            processed_eval = self.eval_dataset.map(
                self._preprocess_function,
                batched=True,
                remove_columns=self.eval_dataset.column_names,
                desc="Processing evaluation data"
            )
            trainer.eval_dataset = processed_eval

        trainer.train()
        logger.info("Training completed!")

        return trainer

    def evaluate(self):
        if self.eval_dataset is None:
            logger.warning("No evaluation dataset provided")
            return None

        logger.info("Starting evaluation...")

        trainer = Trainer(
            model=self.model,
            args=self.training_args,
            eval_dataset=self.eval_dataset,
            data_collator=self.data_collator,
            tokenizer=self.tokenizer,
        )

        processed_eval = self.eval_dataset.map(
            self._preprocess_function,
            batched=True,
            remove_columns=self.eval_dataset.column_names
        )
        trainer.eval_dataset = processed_eval

        results = trainer.evaluate()
        logger.info(f"Evaluation results: {results}")

        return results

    def save_model(self, output_dir: Optional[str] = None):
        save_dir = output_dir or self.config.output_dir
        logger.info(f"Saving model to {save_dir}")

        self.model.module.save_pretrained(save_dir) if hasattr(self.model, 'module') else self.model.save_pretrained(save_dir)
        self.tokenizer.save_pretrained(save_dir)


class LoRALinearLayer(nn.Module):
    def __init__(self, in_features: int, out_features: int, rank: int = 4, alpha: int = 1):
        super().__init__()
        self.rank = rank
        self.alpha = alpha
        self.scaling = alpha / rank

        self.lora_A = nn.Parameter(torch.zeros(in_features, rank))
        self.lora_B = nn.Parameter(torch.zeros(rank, out_features))
        nn.init.normal_(self.lora_A, std=1 / rank)
        nn.init.zeros_(self.lora_B)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x @ self.lora_A @ self.lora_B) * self.scaling


class LoRAModel(nn.Module):
    def __init__(
        self,
        base_model: nn.Module,
        rank: int = 4,
        alpha: int = 1,
        target_modules: Optional[List[str]] = None
    ):
        super().__init__()
        self.base_model = base_model
        self.rank = rank
        self.alpha = alpha
        self.target_modules = target_modules or ["c_attn", "c_proj"]

        self.lora_layers = nn.ModuleDict()
        self._apply_lora()

    def _apply_lora(self):
        for name, module in self.base_model.named_modules():
            if any(target in name for target in self.target_modules):
                if hasattr(module, 'weight'):
                    in_features = module.weight.shape[1]
                    out_features = module.weight.shape[0]
                    lora_layer = LoRALinearLayer(in_features, out_features, self.rank, self.alpha)
                    self.lora_layers[name.replace(".", "_")] = lora_layer

    def forward(self, *args, **kwargs):
        return self.base_model(*args, **kwargs)

    def get_lora_parameters(self):
        return [param for param in self.parameters() if param.requires_grad]


class EarlyStoppingCallback:
    def __init__(self, patience: int = 3, min_delta: float = 0.0):
        self.patience = patience
        self.min_delta = min_delta
        self.best_loss = float('inf')
        self.counter = 0
        self.should_stop = False

    def __call__(self, loss: float) -> bool:
        if loss < self.best_loss - self.min_delta:
            self.best_loss = loss
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
                logger.info(f"Early stopping triggered after {self.counter} evaluations without improvement")
        return self.should_stop


class TrainingMonitor:
    def __init__(self):
        self.train_losses = []
        self.eval_losses = []
        self.learning_rates = []

    def log_training_step(self, step: int, loss: float, lr: float):
        self.train_losses.append({"step": step, "loss": loss})
        self.learning_rates.append({"step": step, "lr": lr})

    def log_evaluation(self, step: int, loss: float):
        self.eval_losses.append({"step": step, "loss": loss})

    def get_best_eval_loss(self) -> Optional[float]:
        if not self.eval_losses:
            return None
        return min(self.eval_losses, key=lambda x: x["loss"])["loss"]

    def summary(self) -> Dict[str, Any]:
        return {
            "total_training_steps": len(self.train_losses),
            "total_eval_steps": len(self.eval_losses),
            "best_eval_loss": self.get_best_eval_loss(),
            "final_training_loss": self.train_losses[-1]["loss"] if self.train_losses else None
        }
