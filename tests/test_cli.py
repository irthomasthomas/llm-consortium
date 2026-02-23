import json
import os
import tempfile
import pytest
from click.testing import CliRunner
import llm
import click
from llm_consortium import register_commands

# Create a dummy CLI group for testing
@click.group()
def cli():
    pass

register_commands(cli)

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
