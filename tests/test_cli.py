import json
import os
import tempfile
import pytest
from click.testing import CliRunner
import llm
import click
from llm_consortium import register_commands
from llm_consortium.db import DatabaseConnection
from llm_consortium.models import _get_consortium_configs

# Create a dummy CLI group for testing
@click.group()
def cli():
    pass

register_commands(cli)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr('llm_consortium.db.user_dir', lambda: tmp_path)
    if hasattr(DatabaseConnection._thread_local, 'db'):
        delattr(DatabaseConnection._thread_local, 'db')
    yield
    if hasattr(DatabaseConnection._thread_local, 'db'):
        delattr(DatabaseConnection._thread_local, 'db')

def test_save_command():
    """Test the 'consortium save' CLI command."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "consortium", "save", "test-consortium",
        "--model", "dummy:1",
        "--arbiter", "dummy",
        "--confidence-threshold", "0.9",
        "--max-iterations", "3",
        "--min-iterations", "2"
    ])
    assert result.exit_code == 0
    assert "test-consortium" in result.output.lower()

def test_save_command_multiple_models():
    """Test save command with multiple models."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "consortium", "save", "multi-model-test",
        "--model", "gpt-4:2",
        "--model", "claude:1",
        "--arbiter", "gemini",
    ])
    assert result.exit_code == 0


def test_save_command_accumulates_repeated_strategy_params():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "consortium", "save", "role-list-test",
        "--model", "dummy:1",
        "--arbiter", "dummy",
        "--strategy", "role",
        "--strategy-param", "roles=Security reviewer",
        "--strategy-param", "roles=Performance reviewer",
    ])

    assert result.exit_code == 0

    config = _get_consortium_configs()["role-list-test"]
    assert config.strategy_params["roles"] == ["Security reviewer", "Performance reviewer"]


def test_save_command_forces_rank_for_elimination():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "consortium", "save", "elim-rank-test",
        "--model", "dummy:1",
        "--model", "dummy:1",
        "--arbiter", "dummy",
        "--strategy", "elimination",
        "--judging-method", "default",
    ])

    assert result.exit_code == 0

    config = _get_consortium_configs()["elim-rank-test"]
    assert config.judging_method == "rank"


def test_strategies_command_lists_built_in_strategies():
    runner = CliRunner()
    result = runner.invoke(cli, ["consortium", "strategies"])

    assert result.exit_code == 0
    assert "Name: default" in result.output
    assert "Name: elimination" in result.output
    assert "Name: role" in result.output
    assert "Name: voting" in result.output


def test_save_command_persists_embedding_configuration():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "consortium", "save", "semantic-test",
        "--model", "dummy:1",
        "--arbiter", "dummy",
        "--strategy", "semantic",
        "--embedding-backend", "chutes",
        "--embedding-model", "qwen3-embedding-8b",
        "--clustering-algorithm", "dbscan",
        "--cluster-eps", "0.5",
    ])

    assert result.exit_code == 0

    config = _get_consortium_configs()["semantic-test"]
    assert config.embedding_backend == "chutes"
    assert config.embedding_model == "qwen3-embedding-8b"
    assert config.strategy == "semantic"
    assert config.strategy_params["clustering_algorithm"] == "dbscan"
    assert float(config.strategy_params["eps"]) == 0.5


def test_config_to_dict_includes_embedding_fields():
    config = _get_consortium_configs()
    assert isinstance(config, dict)

    from llm_consortium.models import ConsortiumConfig

    model_config = ConsortiumConfig(
        models={"dummy": 1},
        arbiter="dummy",
        embedding_backend="chutes",
        embedding_model="qwen3-embedding-8b",
        embedding_cache_enabled=False,
    )

    serialized = model_config.to_dict()
    assert serialized["embedding_backend"] == "chutes"
    assert serialized["embedding_model"] == "qwen3-embedding-8b"
    assert serialized["embedding_cache_enabled"] is False


def test_config_backwards_compatible_without_embedding_fields():
    from llm_consortium.models import ConsortiumConfig

    config = ConsortiumConfig(models={"dummy": 1}, arbiter="dummy")

    assert config.embedding_backend is None
    assert config.embedding_model is None
    assert config.embedding_cache_enabled is True
