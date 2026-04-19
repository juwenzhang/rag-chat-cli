from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union, AsyncIterator
import httpx
import json
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model_name: str = "qwen3:latest"
    temperature: float = 1.0
    top_p: float = 0.9
    top_k: int = 40
    num_predict: int = 256
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None
    stream: bool = False
    timeout: float = 120.0


class OllamaClient:
    def __init__(self, config: Optional[OllamaConfig] = None, verify_connection: bool = True):
        self.config = config or OllamaConfig()
        self.base_url = self.config.base_url.rstrip("/")
        self._client = httpx.Client(timeout=self.config.timeout)
        self._async_client = httpx.AsyncClient(timeout=self.config.timeout)
        if verify_connection:
            self._verify_connection()

    def _verify_connection(self):
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                logger.info(f"Connected to Ollama at {self.base_url}")
            else:
                logger.warning(f"Ollama returned status {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?")

    def is_server_available(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        response = self._client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        logger.debug(f"Available models: {[m['name'] for m in models]}")
        return models

    def pull_model(self, model_name: Optional[str] = None, force: bool = False) -> bool:
        model = model_name or self.config.model_name
        logger.info(f"Checking if model {model} is available...")

        if not force and self.is_model_available(model):
            logger.info(f"Model {model} is already available")
            return True

        logger.info(f"Pulling model: {model} (this may take a few minutes)...")
        try:
            response = self._client.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=600.0
            )

            if response.status_code == 200:
                import time
                time.sleep(2)
                if self.is_model_available(model):
                    logger.info(f"Model {model} pulled successfully")
                    return True
                else:
                    logger.warning(f"Pull returned success but model {model} not found. Retrying with stream...")
                    return self._pull_with_stream(model)
            else:
                logger.error(f"Pull failed with status {response.status_code}: {response.text}")
                return False

        except httpx.RequestError as e:
            logger.error(f"Failed to pull model: {e}")
            return False

    def _pull_with_stream(self, model: str) -> bool:
        try:
            with self._client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": model},
            ) as response:
                response.raise_for_status()
                success_received = False
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "status" in data:
                                logger.info(f"Ollama: {data['status']}")
                            if data.get("status") == "success":
                                success_received = True
                        except json.JSONDecodeError:
                            continue

                if success_received:
                    import time
                    time.sleep(2)
                    if self.is_model_available(model):
                        logger.info(f"Model {model} pulled successfully")
                        return True
            return False
        except httpx.RequestError as e:
            logger.error(f"Failed to pull model with stream: {e}")
            return False

    def is_model_available(self, model_name: str) -> bool:
        try:
            models = self.list_models()
            return any(m["name"] == model_name for m in models)
        except:
            return False

    def ensure_model(self, model_name: Optional[str] = None) -> bool:
        model = model_name or self.config.model_name
        if self.is_model_available(model):
            logger.info(f"Model {model} is ready")
            return True
        return self.pull_model(model)

    def get_status(self) -> Dict[str, Any]:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                return {"status": "running", "models": response.json().get("models", [])}
            return {"status": "error", "message": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": False,
            **kwargs
        }
        response = self._client.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        return response.json()

    def stream_generate(self, prompt: str, callback=None, **kwargs):
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": True,
            **kwargs
        }

        with self._client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            content = data["response"]
                            if callback:
                                callback(content)
                            else:
                                yield content
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    async def agenerate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": False,
            **kwargs
        }
        response = await self._async_client.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        return response.json()

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": False,
            **kwargs
        }
        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama chat error: {e.response.status_code} - {e.response.text}")
            raise

    def stream_chat(self, messages: List[Dict[str, str]], callback=None, **kwargs):
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": True,
            **kwargs
        }

        try:
            with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                content = data["message"]["content"]
                                if callback:
                                    callback(content)
                                else:
                                    yield content
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama stream chat error: {e.response.status_code} - {e.response.text}")
            raise

    async def achat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": False,
            **kwargs
        }
        response = await self._async_client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self):
        self._client.close()
        try:
            loop = None
            try:
                import asyncio
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass
            if loop and loop.is_running():
                import asyncio
                loop.create_task(self._async_client.aclose())
            else:
                asyncio.run(self._async_client.aclose())
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class OllamaModel:
    def __init__(self, config: Optional[OllamaConfig] = None, verify_connection: bool = True):
        self.config = config or OllamaConfig()
        self.client = OllamaClient(self.config, verify_connection=verify_connection)
        if verify_connection:
            self.client.ensure_model()
        self.device = "cpu"

    def ensure_ready(self):
        if not self.client.is_server_available():
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.config.base_url}. "
                "Please ensure Ollama is running. You can start it with: ollama serve"
            )
        self.client.ensure_model()

    def format_prompt(self, instruction: str, input_text: str = "") -> str:
        if input_text:
            return f"Instruction: {instruction}\nInput: {input_text}\nOutput:"
        return f"Instruction: {instruction}\nOutput:"

    def generate(self, prompt: str, **kwargs) -> str:
        response = self.client.generate(prompt=prompt, **kwargs)
        return response.get("response", "")

    def chat(self, instruction: str, input_text: str = "", **kwargs) -> str:
        prompt = self.format_prompt(instruction, input_text)

        messages = [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.client.chat(messages=messages, **kwargs)
            return response.get("message", {}).get("content", "")
        except httpx.HTTPStatusError:
            logger.warning("Chat API failed, falling back to generate API")
            return self.generate(prompt, **kwargs)

    def stream_chat(self, instruction: str, input_text: str = "", callback=None, **kwargs):
        prompt = self.format_prompt(instruction, input_text)

        messages = [
            {"role": "system", "content": "你是一位专业的技术博客写作助手，擅长用简洁清晰的语言解释复杂的技术概念。"},
            {"role": "user", "content": prompt}
        ]

        try:
            return self.client.stream_chat(messages=messages, callback=callback, **kwargs)
        except httpx.HTTPStatusError:
            logger.warning("Stream chat failed, falling back to stream generate")
            return self.stream_generate(prompt, callback=callback, **kwargs)

    def stream_generate(self, prompt: str, callback=None, **kwargs):
        return self.client.stream_generate(prompt=prompt, callback=callback, **kwargs)

    def batch_chat(self, conversations: List[Dict[str, str]], **kwargs) -> List[str]:
        responses = []
        for conv in conversations:
            instruction = conv.get("instruction", "")
            input_text = conv.get("input", "")
            response = self.chat(instruction, input_text, **kwargs)
            responses.append(response)
        return responses

    def save(self, save_directory: Union[str, Path]):
        logger.info("Ollama models are saved in Docker container. Model is already persisted.")

    def load(self, load_directory: Union[str, Path]):
        logger.info("Ollama models are loaded from Docker container.")

    def close(self):
        self.client.close()


class OllamaManager:
    def __init__(self, base_url: str = "http://localhost:11434", verify_connection: bool = False):
        self.base_url = base_url
        self.client = OllamaClient(OllamaConfig(base_url=base_url), verify_connection=verify_connection)

    def pull_model(self, model_name: str, force: bool = False) -> bool:
        return self.client.pull_model(model_name, force=force)

    def list_available_models(self) -> List[str]:
        models = self.client.list_models()
        return [m["name"] for m in models]

    def is_model_available(self, model_name: str) -> bool:
        return self.client.is_model_available(model_name)

    def is_server_available(self) -> bool:
        return self.client.is_server_available()

    def ensure_model(self, model_name: str) -> bool:
        return self.client.ensure_model(model_name)

    def get_status(self) -> Dict[str, Any]:
        return self.client.get_status()
