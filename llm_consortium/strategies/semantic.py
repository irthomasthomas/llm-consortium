"""
Semantic Clustering Strategy for LLM Consortium.
Uses sklearn for clustering if available, otherwise provides a helpful error.
"""
import logging
import json
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

from ..db import save_cluster_metadata, save_response_embedding, DatabaseConnection
from ..geometry import TropicalConsensus, _cosine_distance
from .base import ConsortiumStrategy

logger = logging.getLogger(__name__)


class SemanticClusteringStrategy(ConsortiumStrategy):
    """Cluster responses semantically using embeddings."""
    
    def __init__(self, orchestrator, params=None):
        """Initialize the strategy, checking for optional dependencies."""
        super().__init__(orchestrator, params)
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if sklearn is available when the strategy is used."""
        try:
            from sklearn.cluster import DBSCAN  # noqa: F401
            self._sklearn_available = True
        except ImportError:
            self._sklearn_available = False
            logger.warning(
                "SemanticClusteringStrategy requires sklearn. "
                "Install with: pip install llm-consortium[embeddings]"
            )
    
    def _validate_params(self):
        """Validate and set default parameters."""
        self.clustering_algorithm = str(self.params.get("clustering_algorithm", "dbscan")).strip().lower()
        self.eps = float(self.params.get("eps", 0.5))
        self.min_samples = int(self.params.get("min_samples", 2))
        self.use_centroid_synthesis = bool(self.params.get("use_centroid_synthesis", False))
        
        if self.clustering_algorithm != "dbscan":
            logger.warning(f"Unsupported clustering algorithm: {self.clustering_algorithm}. Using DBSCAN.")
            self.clustering_algorithm = "dbscan"
        
    def _ensure_dependencies(self):
        if not self._sklearn_available:
            raise ImportError(
                "The 'semantic' strategy requires optional dependencies (sklearn).\n"
                "To use semantic clustering, install the embeddings extras:\n"
                "  pip install llm-consortium[embeddings]\n"
                "Or install sklearn directly:\n"
                "  pip install scikit-learn\n"
            )

    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        """Default behavior: use all configured models."""
        return available_models

    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        """Processes, filters, or ranks successful model responses before synthesis."""
        if not successful_responses:
            return []

        self._ensure_dependencies()
        
        # 1. Get embedding service
        try:
            service = self.orchestrator.get_embedding_service()
        except Exception as e:
            logger.error(f"Failed to get embedding service: {e}")
            raise RuntimeError(f"Semantic strategy failed to initialize embedding service: {e}")

        # 2. Get embeddings for responses
        texts = [r.get("response", "") for r in successful_responses]
        try:
            embeddings = service.embed_batch(texts)
        except Exception as e:
            logger.error(f"Failed to embed responses: {e}")
            raise RuntimeError(f"Semantic strategy failed to get embeddings: {e}")

        # 3. Save embeddings if we have a run ID
        run_id = getattr(self.orchestrator, 'consortium_id', None)
        model_name = getattr(self.orchestrator.config, 'embedding_model', "unknown")
        
        for i, (resp, vec) in enumerate(zip(successful_responses, embeddings)):
            resp["embedding"] = vec
            if run_id and "response_id" in resp:
                save_response_embedding(
                    str(resp["response_id"]),
                    str(run_id),
                    vec.tolist(),
                    resp.get("model", "unknown"),
                    embedding_model=model_name
                )

        # 4. Cluster embeddings
        labels = self._cluster_responses(embeddings)
        
        for i, label in enumerate(labels):
            successful_responses[i]["cluster_id"] = label

        # 5. Identify largest cluster (ignoring noise -1)
        cluster_counts = Counter([label for label in labels if label != -1])
        if not cluster_counts:
            logger.info("No semantic clusters found. Returning all responses as outliers.")
            for resp in successful_responses:
                resp["cluster_id"] = -1
                resp["distance_to_centroid"] = 1.0 # Or some large value?
            return successful_responses

        largest_cluster_id = cluster_counts.most_common(1)[0][0]
        logger.info(f"Largest cluster: {largest_cluster_id} with {cluster_counts[largest_cluster_id]} members")

        # 6. Filter to largest cluster
        consensus_responses = [r for r in successful_responses if r.get("cluster_id") == largest_cluster_id]
        
        # 7. Compute centroid and distances
        cluster_embeddings = [r["embedding"] for r in consensus_responses]
        centroid = np.mean(np.vstack(cluster_embeddings), axis=0)
        
        for resp in successful_responses:
            if resp.get("cluster_id") == largest_cluster_id:
                resp["distance_to_centroid"] = _cosine_distance(resp["embedding"], centroid)
            else:
                resp["distance_to_centroid"] = 1.0 # Max distance for outliers

        # 8. Save cluster metadata
        if run_id:
            # Prepare metadata for all found clusters
            all_cluster_ids = set(labels)
            metadata = []
            for cid in all_cluster_ids:
                if cid == -1: continue
                c_responses = [successful_responses[i] for i, label in enumerate(labels) if label == cid]
                c_embeddings = [r["embedding"] for r in c_responses]
                c_centroid = np.mean(np.vstack(c_embeddings), axis=0)
                
                # Calculate density (1 - mean distance)
                c_distances = [_cosine_distance(vec, c_centroid) for vec in c_embeddings]
                density = 1.0 - float(np.mean(c_distances))
                
                metadata.append({
                    "cluster_id": int(cid),
                    "centroid": c_centroid.tolist(),
                    "density": density,
                    "radius": float(np.max(c_distances)) if c_distances else 0.0
                })
            save_cluster_metadata(str(run_id), iteration, metadata)

        return consensus_responses

    def _cluster_responses(self, embeddings: List[np.ndarray]) -> List[int]:
        """Cluster embeddings using DBSCAN."""
        self._ensure_dependencies()
        from sklearn.cluster import DBSCAN
        
        embeddings_array = np.vstack(embeddings)
        clustering = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine').fit(embeddings_array)
        return clustering.labels_.tolist()
