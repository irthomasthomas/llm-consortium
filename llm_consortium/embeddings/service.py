import hashlib
import logging
import threading
from collections import OrderedDict
from typing import Optional, Sequence

import numpy as np

from .backends import BaseEmbeddingBackend, ChutesBackend, OpenAIBackend, SentenceTransformerBackend

logger = logging.getLogger(__name__)


class DummyEmbeddingBackend(BaseEmbeddingBackend):
    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def embed(self, text: str) -> np.ndarray:
        return _deterministic_dummy_embedding(text, self._dimension)

    def dimension(self) -> int:
        return self._dimension


def _deterministic_dummy_embedding(text: str, dimension: int) -> np.ndarray:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [(digest[index % len(digest)] / 255.0) for index in range(dimension)]
    vector = np.array(values, dtype=float)
    norm = np.linalg.norm(vector)
    return vector if norm == 0 else vector / norm


class EmbeddingService:
    def __init__(self, backend: BaseEmbeddingBackend, cache_enabled: bool = True, cache_size: int = 256):
        self.backend = backend
        self.cache_enabled = cache_enabled
        self.cache_size = cache_size
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> np.ndarray:
        cache_key = self._cache_key(text)
        if self.cache_enabled:
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    self._cache.move_to_end(cache_key)
                    return cached.copy()

        try:
            vector = self.backend.embed(text)
        except Exception as exc:
            logger.warning("Embedding backend failed for text hash %s: %s", cache_key, exc)
            vector = _deterministic_dummy_embedding(text, self.backend.dimension())

        if self.cache_enabled:
            with self._lock:
                self._cache[cache_key] = vector.copy()
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        return vector

    def embed_batch(self, texts: Sequence[str]) -> list[np.ndarray]:
        return [self.embed(text) for text in texts]


def create_embedding_service(config) -> EmbeddingService:
    backend_name = getattr(config, "embedding_backend", None)
    model_name = getattr(config, "embedding_model", None)
    cache_enabled = getattr(config, "embedding_cache_enabled", True)

    if backend_name == "openai":
        backend = OpenAIBackend(model=model_name or "text-embedding-3-small")
    elif backend_name == "sentence-transformers":
        backend = SentenceTransformerBackend(model=model_name or "all-MiniLM-L6-v2")
    elif backend_name == "chutes":
        backend = ChutesBackend(model=model_name)
    else:
        backend = DummyEmbeddingBackend()

    return EmbeddingService(backend=backend, cache_enabled=cache_enabled)