import pathlib

import numpy as np
import pytest

from llm_consortium.db import DatabaseConnection, save_consortium_run, save_response_embedding, save_run_visualization
from llm_consortium.visualization import EmbeddingProjector, generate_run_visualization


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path: pathlib.Path):
    monkeypatch.setattr("llm_consortium.db.user_dir", lambda: tmp_path)
    if hasattr(DatabaseConnection._thread_local, "db"):
        delattr(DatabaseConnection._thread_local, "db")
    yield
    if hasattr(DatabaseConnection._thread_local, "db"):
        delattr(DatabaseConnection._thread_local, "db")


def test_project_tsne_returns_two_dimensions():
    embeddings = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])

    projected = EmbeddingProjector().project_tsne(embeddings, perplexity=2)

    assert projected.shape == (3, 2)


def test_generate_run_visualization_returns_figure():
    save_response_embedding("resp-1", "run-viz", [1.0, 0.0, 0.0], "model-a")
    save_response_embedding("resp-2", "run-viz", [0.0, 1.0, 0.0], "model-b")

    figure = generate_run_visualization("run-viz")

    assert hasattr(figure, "to_html") or hasattr(figure, "savefig")


def test_save_run_visualization_persists_cached_payload():
    save_run_visualization("run-visual", '{"points": []}')

    db = DatabaseConnection.get_connection()
    row = db["consortium_runs"].get("run-visual")

    assert row["visualization_json"] == '{"points": []}'


def test_save_run_visualization_preserves_existing_run_metadata():
    save_consortium_run(
        run_id="run-existing",
        strategy="semantic",
        judging_method="default",
        confidence_threshold=0.8,
        max_iterations=3,
        iteration_count=2,
        final_confidence=0.91,
        user_prompt="Preserve me",
        config_name="semantic-existing",
    )

    save_run_visualization("run-existing", '{"points": [1]}')

    row = DatabaseConnection.get_connection()["consortium_runs"].get("run-existing")

    assert row["strategy"] == "semantic"
    assert row["user_prompt"] == "Preserve me"
    assert row["iteration_count"] == 2
    assert row["final_confidence"] == 0.91
    assert row["visualization_json"] == '{"points": [1]}'