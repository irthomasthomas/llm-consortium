import hashlib
import sys
import types

import numpy as np
import pytest

from llm_consortium.embeddings.backends import (
    BaseEmbeddingBackend,
    ChutesBackend,
    OpenAIBackend,
    SentenceTransformerBackend,
)
from llm_consortium.embeddings.service import EmbeddingService


class DummyBackend(BaseEmbeddingBackend):
    def __init__(self):
        self.calls = 0

    def embed(self, text: str) -> np.ndarray:
        self.calls += 1
        return np.array([float(len(text)), 1.0, 2.0], dtype=float)

    def dimension(self) -> int:
        return 3


def test_embedding_backend_contract():
    backend = DummyBackend()
    vector = backend.embed("hello")

    assert isinstance(backend, BaseEmbeddingBackend)
    assert isinstance(vector, np.ndarray)
    assert backend.dimension() == 3


def test_openai_backend_uses_embeddings_api(monkeypatch):
    class Response:
        data = [types.SimpleNamespace(embedding=[0.1, 0.2, 0.3])]

    class Embeddings:
        @staticmethod
        def create(*, input, model):
            assert input == "hello"
            assert model == "text-embedding-3-small"
            return Response()

    fake_openai = types.SimpleNamespace(embeddings=Embeddings())
    monkeypatch.setattr("llm_consortium.embeddings.backends.openai", fake_openai)

    backend = OpenAIBackend(model="text-embedding-3-small")
    vector = backend.embed("hello")

    assert np.allclose(vector, np.array([0.1, 0.2, 0.3]))
    assert backend.dimension() == 1536


def test_sentence_transformer_backend_uses_model_dimension(monkeypatch):
    class FakeModel:
        def encode(self, text):
            assert text == "hello"
            return [0.4, 0.5, 0.6]

        def get_sentence_embedding_dimension(self):
            return 384

    fake_module = types.SimpleNamespace(SentenceTransformer=lambda model_name: FakeModel())
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    backend = SentenceTransformerBackend(model="all-MiniLM-L6-v2")
    vector = backend.embed("hello")

    assert np.allclose(vector, np.array([0.4, 0.5, 0.6]))
    assert backend.dimension() == 384


def test_chutes_backend_calls_qwen_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.7, 0.8]}]}

    class FakeClient:
        def post(self, url, headers, json, timeout):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse()

    monkeypatch.setenv("CHUTES_API_TOKEN", "token")

    backend = ChutesBackend(client=FakeClient())
    vector = backend.embed("hello")

    assert np.allclose(vector, np.array([0.7, 0.8]))
    assert calls[0]["url"].endswith("/v1/embeddings")
    assert calls[0]["json"] == {"input": "hello", "model": None}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"


def test_embedding_service_caches_by_text_hash():
    backend = DummyBackend()
    service = EmbeddingService(backend=backend, cache_enabled=True, cache_size=8)

    first = service.embed("repeat")
    second = service.embed("repeat")

    assert np.allclose(first, second)
    assert backend.calls == 1
    assert hashlib.sha256("repeat".encode("utf-8")).hexdigest() in service._cache


def test_embedding_service_gracefully_degrades_on_failure():
    class FailingBackend(BaseEmbeddingBackend):
        def embed(self, text: str) -> np.ndarray:
            raise RuntimeError("boom")

        def dimension(self) -> int:
            return 4

    service = EmbeddingService(backend=FailingBackend(), cache_enabled=False)
    vector = service.embed("fallback")

    assert isinstance(vector, np.ndarray)
    assert vector.shape == (4,)
    assert np.linalg.norm(vector) > 0.0