from types import SimpleNamespace

import numpy as np

from llm_consortium.strategies.base import ConsortiumStrategy
from llm_consortium.strategies.semantic import SemanticClusteringStrategy


class StubEmbeddingService:
    def __init__(self, mapping):
        self.mapping = mapping

    def embed(self, text: str) -> np.ndarray:
        return np.array(self.mapping[text], dtype=float)

    def embed_batch(self, texts):
        return [self.embed(text) for text in texts]


def _make_orchestrator(mapping):
    return SimpleNamespace(
        consortium_id="run-semantic",
        config=SimpleNamespace(embedding_model="qwen3-embedding-8b"),
        get_embedding_service=lambda: StubEmbeddingService(mapping),
    )


def test_semantic_strategy_inherits_base_class():
    strategy = SemanticClusteringStrategy(_make_orchestrator({}))
    assert isinstance(strategy, ConsortiumStrategy)


def test_validate_params_accepts_supported_algorithms():
    strategy = SemanticClusteringStrategy(
        _make_orchestrator({}),
        {
            "clustering_algorithm": "dbscan",
            "eps": 0.4,
            "min_samples": 2,
            "use_centroid_synthesis": True,
        },
    )

    assert strategy.clustering_algorithm == "dbscan"
    assert strategy.eps == 0.4
    assert strategy.min_samples == 2
    assert strategy.use_centroid_synthesis is True


def test_process_responses_filters_to_largest_cluster():
    mapping = {
        "cluster-a-1": [1.0, 0.0],
        "cluster-a-2": [0.95, 0.05],
        "outlier": [-1.0, 0.0],
    }
    strategy = SemanticClusteringStrategy(
        _make_orchestrator(mapping),
        {"clustering_algorithm": "dbscan", "eps": 0.2, "min_samples": 2},
    )
    responses = [
        {"response": "cluster-a-1", "id": 1, "response_id": "r1", "model": "m1"},
        {"response": "cluster-a-2", "id": 2, "response_id": "r2", "model": "m2"},
        {"response": "outlier", "id": 3, "response_id": "r3", "model": "m3"},
    ]

    filtered = strategy.process_responses(responses, iteration=1)

    assert [response["response"] for response in filtered] == ["cluster-a-1", "cluster-a-2"]
    assert all("embedding" in response for response in filtered)
    assert all(response["cluster_id"] == 0 for response in filtered)
    assert all("distance_to_centroid" in response for response in filtered)


def test_process_responses_falls_back_to_all_when_everything_is_outlier():
    mapping = {
        "a": [1.0, 0.0],
        "b": [0.0, 1.0],
        "c": [-1.0, 0.0],
    }
    strategy = SemanticClusteringStrategy(
        _make_orchestrator(mapping),
        {"clustering_algorithm": "dbscan", "eps": 0.01, "min_samples": 2},
    )
    responses = [
        {"response": "a", "id": 1, "response_id": "r1", "model": "m1"},
        {"response": "b", "id": 2, "response_id": "r2", "model": "m2"},
        {"response": "c", "id": 3, "response_id": "r3", "model": "m3"},
    ]

    filtered = strategy.process_responses(responses, iteration=1)

    assert len(filtered) == 3
    assert {response["cluster_id"] for response in filtered} == {-1}