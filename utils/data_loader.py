from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import pandas as pd
from datasets import Dataset, load_dataset as hf_load_dataset
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DataLoaderConfig:
    file_path: str
    file_type: str = "json"
    num_proc: int = 4
    batch_size: int = 1000
    shuffle: bool = False
    seed: Optional[int] = None


class BaseDataLoader(ABC):
    def __init__(self, config: DataLoaderConfig):
        self.config = config

    @abstractmethod
    def load(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def save(self, data: List[Dict[str, Any]], path: str):
        pass


class JSONDataLoader(BaseDataLoader):
    def load(self) -> List[Dict[str, Any]]:
        logger.info(f"Creating JSONDataLoader for {self.config.file_path}")

        import json
        try:
            with open(self.config.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            elif not isinstance(data, list):
                data = [data]
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise RuntimeError(f"Failed to parse JSON file: {e}")

        logger.info(f"Loaded {len(data)} records from JSON")
        return data

    def save(self, data: List[Dict[str, Any]], path: str):
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(data)} records to {path}")


class CSVDataLoader(BaseDataLoader):
    def load(self) -> List[Dict[str, Any]]:
        logger.info(f"Loading CSV from {self.config.file_path}")

        df = pd.read_csv(self.config.file_path)
        data = df.to_dict("records")
        logger.info(f"Loaded {len(data)} records from CSV")
        return data

    def save(self, data: List[Dict[str, Any]], path: str):
        df = pd.DataFrame(data)
        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"Saved {len(data)} records to {path}")


class DataLoaderFactory:
    @staticmethod
    def create(config: DataLoaderConfig) -> BaseDataLoader:
        loaders = {
            "json": JSONDataLoader,
            "csv": CSVDataLoader,
        }

        loader_class = loaders.get(config.file_type.lower())
        if not loader_class:
            raise ValueError(f"Unsupported file type: {config.file_type}")

        return loader_class(config)


class DatasetSplitter:
    def __init__(self, dataset: List[Dict], train_ratio: float = 0.8, seed: Optional[int] = None):
        self.dataset = dataset
        self.train_ratio = train_ratio
        self.seed = seed

    def split(self) -> tuple:
        import random
        if self.seed:
            random.seed(self.seed)

        data = self.dataset.copy()
        random.shuffle(data)

        split_idx = int(len(data) * self.train_ratio)
        train_data = data[:split_idx]
        eval_data = data[split_idx:]

        logger.info(f"Split dataset: {len(train_data)} train, {len(eval_data)} eval")
        return train_data, eval_data
