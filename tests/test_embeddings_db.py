import pathlib

import numpy as np
import pytest

from llm_consortium.db import (
    DatabaseConnection,
    get_embeddings_for_run,
    save_cluster_metadata,
    save_response_embedding,
)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path: pathlib.Path):
    monkeypatch.setattr("llm_consortium.db.user_dir", lambda: tmp_path)
    if hasattr(DatabaseConnection._thread_local, "db"):
        delattr(DatabaseConnection._thread_local, "db")
    yield
    if hasattr(DatabaseConnection._thread_local, "db"):
        delattr(DatabaseConnection._thread_local, "db")


def test_save_response_embedding_creates_table_and_round_trips_vector():
    save_response_embedding(
        response_id="resp-1",
        run_id="run-1",
        vector=[0.1, 0.2, 0.3],
        model="model-a",
        embedding_model="qwen3-embedding-8b",
    )

    db = DatabaseConnection.get_connection()
    row = db["response_embeddings"].get("resp-1")

    assert row["run_id"] == "run-1"
    assert row["model"] == "model-a"
    assert row["embedding_model"] == "qwen3-embedding-8b"

    embeddings = get_embeddings_for_run("run-1")
    assert len(embeddings) == 1
    assert np.allclose(embeddings[0], np.array([0.1, 0.2, 0.3]))


def test_save_cluster_metadata_creates_consensus_clusters_table():
    save_cluster_metadata(
        run_id="run-2",
        iteration=2,
        clusters=[
            {
                "cluster_id": 7,
                "centroid": [1.0, 2.0],
                "radius": 0.4,
                "density": 3.5,
            }
        ],
    )

    db = DatabaseConnection.get_connection()
    rows = list(db["consensus_clusters"].rows)

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-2"
    assert rows[0]["iteration"] == 2
    assert rows[0]["cluster_id"] == 7
    assert rows[0]["radius"] == 0.4
    assert rows[0]["density"] == 3.5


def test_embedding_and_decision_writes_are_migration_safe():
    db = DatabaseConnection.get_connection()
    db["response_embeddings"].insert(
        {
            "response_id": "legacy-1",
            "run_id": "legacy-run",
            "model": "legacy-model",
            "embedding_json": "[0.0, 1.0]",
        },
        pk="response_id",
        replace=True,
    )

    save_response_embedding(
        response_id="legacy-1",
        run_id="legacy-run",
        vector=[0.0, 1.0],
        model="legacy-model",
        embedding_model="qwen3-embedding-8b",
    )

    columns = {column.name for column in db["response_embeddings"].columns}
    assert "embedding_model" in columns
    assert "created_at" in columns