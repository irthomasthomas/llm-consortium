import abc
import os
from typing import Optional, Protocol

import httpx
import numpy as np
import openai


class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> np.ndarray:
        ...

    def dimension(self) -> int:
        ...


class BaseEmbeddingBackend(abc.ABC):
    @abc.abstractmethod
    def embed(self, text: str) -> np.ndarray:
        raise NotImplementedError

    @abc.abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError


class OpenAIBackend(BaseEmbeddingBackend):
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._dimension = 1536

    def embed(self, text: str) -> np.ndarray:
        if hasattr(openai, "embeddings") and hasattr(openai.embeddings, "create"):
            response = openai.embeddings.create(input=text, model=self.model)
        else:
            client = openai.OpenAI()
            response = client.embeddings.create(input=text, model=self.model)
        return np.array(response.data[0].embedding, dtype=float)

    def dimension(self) -> int:
        return self._dimension


class SentenceTransformerBackend(BaseEmbeddingBackend):
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model_name = model
        self._model = SentenceTransformer(model)
        self._dimension = int(self._model.get_sentence_embedding_dimension() or 384)

    def embed(self, text: str) -> np.ndarray:
        return np.array(self._model.encode(text), dtype=float)

    def dimension(self) -> int:
        return self._dimension


class ChutesBackend(BaseEmbeddingBackend):
    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        endpoint: str = "https://chutes-qwen-qwen3-embedding-8b.chutes.ai/v1/embeddings",
        model: Optional[str] = None,
        default_dimension: int = 1024,
    ):
        self.client = client or httpx.Client()
        self.endpoint = endpoint
        self.model = model
        self._dimension = default_dimension

    def embed(self, text: str) -> np.ndarray:
        token = os.environ.get("CHUTES_API_TOKEN")
        if not token:
            raise RuntimeError("CHUTES_API_TOKEN is required for the chutes embedding backend")

        response = self.client.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"input": text, "model": self.model},
            timeout=30,
        )
        response.raise_for_status()
        vector = np.array(response.json()["data"][0]["embedding"], dtype=float)
        self._dimension = int(vector.shape[0])
        return vector

    def dimension(self) -> int:
        return self._dimension