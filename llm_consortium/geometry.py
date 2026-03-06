from typing import List, Tuple

import numpy as np


def _cosine_distance(vector: np.ndarray, centroid: np.ndarray) -> float:
    left_norm = np.linalg.norm(vector)
    right_norm = np.linalg.norm(centroid)
    if left_norm == 0 or right_norm == 0:
        return 1.0
    similarity = float(np.dot(vector, centroid) / (left_norm * right_norm))
    similarity = max(-1.0, min(1.0, similarity))
    return (1.0 - similarity) / 2.0


class TropicalConsensus:
    @staticmethod
    def compute_tropical_centroid(vectors: List[np.ndarray]) -> np.ndarray:
        if not vectors:
            return np.array([], dtype=float)
        matrix = np.vstack(vectors)
        return np.max(matrix, axis=0)


class GeometricConfidenceCalculator:
    @staticmethod
    def compute_confidence(response_vectors: List[np.ndarray], centroid: np.ndarray) -> float:
        if not response_vectors or centroid.size == 0:
            return 0.0
        distances = [_cosine_distance(vector, centroid) for vector in response_vectors]
        mean_distance = float(np.mean(distances)) if distances else 1.0
        return max(0.0, min(1.0, 1.0 - mean_distance))

    @staticmethod
    def detect_outliers(vectors: List[np.ndarray], threshold_std: float = 2.0) -> List[int]:
        if len(vectors) < 3:
            return []
        centroid = np.mean(np.vstack(vectors), axis=0)
        distances = np.array([_cosine_distance(vector, centroid) for vector in vectors], dtype=float)
        mean_distance = float(np.mean(distances))
        std_distance = float(np.std(distances))
        if std_distance == 0.0:
            return []
        cutoff = mean_distance + (threshold_std * std_distance)
        return [index for index, distance in enumerate(distances.tolist()) if distance > cutoff]

    @staticmethod
    def compute(response_embeddings: List[np.ndarray]) -> Tuple[float, np.ndarray]:
        if not response_embeddings:
            return 0.0, np.array([], dtype=float)
        centroid = np.mean(np.vstack(response_embeddings), axis=0)
        confidence = GeometricConfidenceCalculator.compute_confidence(response_embeddings, centroid)
        return confidence, centroid