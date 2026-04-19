from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union
import torch
from torch import nn
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    AutoConfig,
    PreTrainedModel,
    PreTrainedTokenizer
)
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    model_name_or_path: str = "gpt2"
    use_cache: bool = True
    pad_token_id: Optional[int] = None
    eos_token_id: Optional[int] = None
    max_length: int = 512
    temperature: float = 1.0
    top_p: float = 1.0
    top_k: int = 50
    num_beams: int = 1
    repetition_penalty: float = 1.0
    device: Optional[str] = None

    def __post_init__(self):
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"


class BaseModel(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self._model: Optional[PreTrainedModel] = None
        self._tokenizer: Optional[PreTrainedTokenizer] = None

    def build(self):
        self._load_tokenizer()
        self._load_model()
        self._setup_device()
        return self

    def _load_tokenizer(self):
        logger.info(f"Loading tokenizer from {self.config.model_name_or_path}")
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_name_or_path
        )
        if self.config.pad_token_id is not None:
            self._tokenizer.pad_token_id = self.config.pad_token_id
        elif self._tokenizer.pad_token_id is None:
            self._tokenizer.pad_token_id = self._tokenizer.eos_token_id

    def _load_model(self):
        logger.info(f"Loading model from {self.config.model_name_or_path}")
        self._model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name_or_path
        )
        self._model.config.use_cache = self.config.use_cache

    def _setup_device(self):
        self.device = torch.device(self.config.device)
        self.to(self.device)

    def tokenize(
        self,
        texts: Union[str, List[str]],
        padding: bool = True,
        truncation: bool = True,
        max_length: Optional[int] = None,
        return_tensors: str = "pt"
    ) -> Dict[str, torch.Tensor]:
        if isinstance(texts, str):
            texts = [texts]

        max_len = max_length or self.config.max_length

        encodings = self._tokenizer(
            texts,
            padding=padding,
            truncation=truncation,
            max_length=max_len,
            return_tensors=return_tensors
        )
        return encodings

    def generate(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        max_length: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        num_beams: Optional[int] = None,
        repetition_penalty: Optional[float] = None,
        **kwargs
    ) -> torch.Tensor:
        self._model.eval()

        gen_kwargs = {
            "max_length": max_length or self.config.max_length,
            "temperature": temperature or self.config.temperature,
            "top_p": top_p or self.config.top_p,
            "top_k": top_k or self.config.top_k,
            "num_beams": num_beams or self.config.num_beams,
            "repetition_penalty": repetition_penalty or self.config.repetition_penalty,
            "pad_token_id": self._tokenizer.pad_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }
        gen_kwargs.update(kwargs)

        with torch.no_grad():
            output_ids = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                **gen_kwargs
            )
        return output_ids

    def generate_text(
        self,
        prompt: str,
        max_length: Optional[int] = None,
        **kwargs
    ) -> str:
        inputs = self.tokenize([prompt], return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)

        output_ids = self.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_length=max_length,
            **kwargs
        )

        generated_text = self._tokenizer.decode(
            output_ids[0],
            skip_special_tokens=True
        )
        return generated_text

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        labels: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        outputs = self._model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels
        )
        return {
            "loss": outputs.loss if labels is not None else None,
            "logits": outputs.logits,
            "hidden_states": outputs.hidden_states if hasattr(outputs, "hidden_states") else None
        }

    def save(self, save_directory: Union[str, Path]):
        save_path = Path(save_directory)
        save_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving model to {save_path}")
        self._model.save_pretrained(save_path)
        self._tokenizer.save_pretrained(save_path)

    def load(self, load_directory: Union[str, Path]):
        logger.info(f"Loading model from {load_directory}")
        self._model = AutoModelForCausalLM.from_pretrained(load_directory)
        self._tokenizer = AutoTokenizer.from_pretrained(load_directory)
        self._setup_device()

    @property
    def model(self) -> PreTrainedModel:
        return self._model

    @property
    def tokenizer(self) -> PreTrainedTokenizer:
        return self._tokenizer

    @property
    def device_obj(self) -> torch.device:
        return self.device


class ChatModel(BaseModel):
    def __init__(self, config: ModelConfig):
        super().__init__(config)

    def build(self):
        super().build()
        logger.info("ChatModel built successfully")
        return self

    def format_prompt(self, instruction: str, input_text: str = "") -> str:
        if input_text:
            return f"Instruction: {instruction}\nInput: {input_text}\nOutput:"
        return f"Instruction: {instruction}\nOutput:"

    def chat(
        self,
        instruction: str,
        input_text: str = "",
        max_length: Optional[int] = None
    ) -> str:
        prompt = self.format_prompt(instruction, input_text)
        response = self.generate_text(prompt, max_length=max_length)
        response = response.split("Output:")[-1].strip()
        return response

    def batch_chat(
        self,
        conversations: List[Dict[str, str]],
        max_length: Optional[int] = None
    ) -> List[str]:
        prompts = [
            self.format_prompt(conv.get("instruction", ""), conv.get("input", ""))
            for conv in conversations
        ]

        inputs = self.tokenize(prompts, return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)

        output_ids = self.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_length=max_length
        )

        responses = []
        for i, output in enumerate(output_ids):
            text = self._tokenizer.decode(output, skip_special_tokens=True)
            response = text.split("Output:")[-1].strip()
            responses.append(response)

        return responses


class ModelFactory:
    _models = {
        "causal_lm": BaseModel,
        "chat": ChatModel,
    }

    @classmethod
    def register(cls, name: str, model_class: type):
        if not issubclass(model_class, BaseModel):
            raise TypeError(f"{model_class} must be a subclass of BaseModel")
        cls._models[name] = model_class
        logger.info(f"Registered model class '{name}': {model_class.__name__}")

    @classmethod
    def create(cls, model_type: str = "chat", **kwargs) -> BaseModel:
        if model_type not in cls._models:
            supported = ", ".join(cls._models.keys())
            raise ValueError(f"Unknown model type '{model_type}'. Supported: {supported}")

        model_class = cls._models[model_type]
        config = ModelConfig(**kwargs)
        model = model_class(config)
        return model.build()


class ModelManager:
    def __init__(self):
        self.models: Dict[str, BaseModel] = {}

    def register_model(self, name: str, model: BaseModel):
        self.models[name] = model
        logger.info(f"Registered model: {name}")

    def get_model(self, name: str) -> BaseModel:
        if name not in self.models:
            raise KeyError(f"Model '{name}' not found")
        return self.models[name]

    def load_model(self, name: str, load_directory: Union[str, Path], model_type: str = "chat"):
        model = ModelFactory.create(model_type)
        model.load(load_directory)
        self.register_model(name, model)

    def save_model(self, name: str, save_directory: Union[str, Path]):
        if name not in self.models:
            raise KeyError(f"Model '{name}' not found")
        self.models[name].save(save_directory)
