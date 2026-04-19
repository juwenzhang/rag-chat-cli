from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json
from pathlib import Path


class PipelineStep(Enum):
    CHECK_MODEL = "check_model"
    LOAD_DATA = "load_data"
    INIT_MODEL = "init_model"
    RUN_INFERENCE = "run_inference"


@dataclass
class DataConfig:
    file_path: str = "./data/train.json"
    file_type: str = "json"
    num_proc: int = 4
    batch_size: int = 1000


@dataclass
class ModelConfig:
    model_name: str = "qwen3:latest"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    top_p: float = 0.9
    num_predict: int = 256


@dataclass
class InferenceConfig:
    num_samples: int = 3
    test_instruction: str = ""
    test_input: str = ""


@dataclass
class PipelineConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    data: DataConfig = field(default_factory=DataConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    steps: List[PipelineStep] = field(default_factory=lambda: [
        PipelineStep.CHECK_MODEL,
        PipelineStep.LOAD_DATA,
        PipelineStep.INIT_MODEL,
        PipelineStep.RUN_INFERENCE
    ])
    max_workers: int = 4

    @classmethod
    def from_json(cls, path: str) -> "PipelineConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            model=ModelConfig(**data.get("model", {})),
            data=DataConfig(**data.get("data", {})),
            inference=InferenceConfig(**data.get("inference", {})),
            steps=[PipelineStep(s) for s in data.get("steps", [])] or cls().steps,
            max_workers=data.get("max_workers", 4)
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        return cls(
            model=ModelConfig(**data.get("model", {})),
            data=DataConfig(**data.get("data", {})),
            inference=InferenceConfig(**data.get("inference", {})),
            steps=[PipelineStep(s) for s in data.get("steps", [])] or cls().steps,
            max_workers=data.get("max_workers", 4)
        )

    def to_json(self, path: str):
        data = {
            "model": self.model.__dict__,
            "data": self.data.__dict__,
            "inference": self.inference.__dict__,
            "steps": [s.value for s in self.steps],
            "max_workers": self.max_workers
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model.__dict__,
            "data": self.data.__dict__,
            "inference": self.inference.__dict__,
            "steps": [s.value for s in self.steps],
            "max_workers": self.max_workers
        }


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def load_config(path: Optional[str] = None) -> PipelineConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if config_path.exists():
        return PipelineConfig.from_json(str(config_path))
    return PipelineConfig()


def save_config(config: PipelineConfig, path: Optional[str] = None):
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config.to_json(str(config_path))
