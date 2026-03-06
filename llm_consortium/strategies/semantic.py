import logging
from collections import Counter
from typing import Any, Dict, List

import numpy as np
from sklearn.cluster import DBSCAN

from ..db import save_cluster_metadata, save_response_embedding
from ..geometry import TropicalConsensus
from .base import ConsortiumStrategy

logger = logging.getLogger(__name__)


class SemanticClusteringStrategy(ConsortiumStrategy):
    def _validate_params(self):
        self.clustering_algorithm = str(self.params.get("clustering_algorithm", "dbscan")).strip().lower()
        self.eps = float(self.params.get("eps", 0.5))
        self.min_samples = int(self.params.get("min_samples", 2))
        self.use_centroid_synthesis = bool(self.params.get("use_centroid_synthesis", False))

        if self.clustering_algorithm not in {"dbscan", "hdbscan", "tropical"}:
            raise ValueError("clustering_algorithm must be one of: dbscan, hdbscan, tropical")
        if self.eps <= 0:
            raise ValueError("eps must be positive")
        if self.min_samples < 1:
            raise ValueError("min_samples must be at least 1")

    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        return available_models.copy()

    def _cluster_vectors(self, vectors: List[np.ndarray]) -> np.ndarray:
        if self.clustering_algorithm == "tropical":
            return np.zeros(len(vectors), dtype=int)

        if self.clustering_algorithm == "hdbscan":
            try:
                import hdbscan  # type: ignore

                clusterer = hdbscan.HDBSCAN(min_cluster_size=max(self.min_samples, 2), metric="euclidean")
                return np.array(clusterer.fit_predict(np.vstack(vectors)), dtype=int)
            except Exception:
                logger.warning("hdbscan unavailable; falling back to dbscan")

        clusterer = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric="euclidean")
        return np.array(clusterer.fit_predict(np.vstack(vectors)), dtype=int)

    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        if not successful_responses:
            return []

        embedding_service = self.orchestrator.get_embedding_service()
        vectors = embedding_service.embed_batch([response.get("response", "") for response in successful_responses])
        labels = self._cluster_vectors(vectors)

        label_counts = Counter(label for label in labels.tolist() if label != -1)
        if not label_counts:
            for response, vector in zip(successful_responses, vectors):
                response["embedding"] = vector
                response["cluster_id"] = -1
                response["distance_to_centroid"] = None
                self._persist_embedding(response, vector)
            return successful_responses

        selected_label = max(label_counts.items(), key=lambda item: item[1])[0]
        selected_vectors = [vector for vector, label in zip(vectors, labels.tolist()) if label == selected_label]
        centroid = self._compute_centroid(selected_vectors)

        filtered: List[Dict[str, Any]] = []
        for response, vector, label in zip(successful_responses, vectors, labels.tolist()):
            response["embedding"] = vector
            response["cluster_id"] = int(label)
            if label == selected_label:
                response["distance_to_centroid"] = float(np.linalg.norm(vector - centroid))
                filtered.append(response)
            else:
                response["distance_to_centroid"] = None
            self._persist_embedding(response, vector)

        if getattr(self.orchestrator, "consortium_id", None):
            distances = [float(np.linalg.norm(vector - centroid)) for vector in selected_vectors]
            save_cluster_metadata(
                run_id=str(self.orchestrator.consortium_id),
                iteration=iteration,
                clusters=[{
                    "cluster_id": int(selected_label),
                    "centroid": centroid.tolist(),
                    "radius": max(distances) if distances else 0.0,
                    "density": float(len(selected_vectors)),
                }],
            )
        return filtered or successful_responses

    def _compute_centroid(self, vectors: List[np.ndarray]) -> np.ndarray:
        if self.clustering_algorithm == "tropical" or self.use_centroid_synthesis:
            return TropicalConsensus.compute_tropical_centroid(vectors)
        return np.mean(np.vstack(vectors), axis=0)

    def _persist_embedding(self, response: Dict[str, Any], vector: np.ndarray) -> None:
        run_id = getattr(self.orchestrator, "consortium_id", None)
        if not run_id:
            return
        response_id = str(response.get("response_id") or response.get("id"))
        save_response_embedding(
            response_id=response_id,
            run_id=str(run_id),
            vector=vector.tolist(),
            model=response.get("model", "unknown"),
            embedding_model=getattr(self.orchestrator.config, "embedding_model", None),
        )