import numpy as np

from llm_consortium.geometry import GeometricConfidenceCalculator


def test_compute_confidence_uses_inverse_average_cosine_distance():
    vectors = [
        np.array([1.0, 0.0]),
        np.array([0.9, 0.1]),
        np.array([0.8, 0.2]),
    ]
    centroid = np.array([0.9, 0.1])

    confidence = GeometricConfidenceCalculator.compute_confidence(vectors, centroid)

    assert 0.8 <= confidence <= 1.0


def test_detect_outliers_returns_far_indices():
    vectors = [
        np.array([1.0, 0.0]),
        np.array([0.95, 0.05]),
        np.array([-1.0, 0.0]),
    ]

    outliers = GeometricConfidenceCalculator.detect_outliers(vectors, threshold_std=0.5)

    assert outliers == [2]


def test_compute_returns_confidence_and_centroid():
    vectors = [
        np.array([1.0, 0.0]),
        np.array([0.0, 1.0]),
    ]

    confidence, centroid = GeometricConfidenceCalculator.compute(vectors)

    assert isinstance(confidence, float)
    assert isinstance(centroid, np.ndarray)
    assert centroid.shape == (2,)