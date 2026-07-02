"""Tests for the learning loop module."""
import pytest
import json
from unittest.mock import patch, MagicMock
from llm_consortium.learning import learn_from_history, format_rules_report, canonical_model, MIN_BATTLES_RELIABLE


def test_canonical_model_known_alias():
    assert canonical_model("glm-5.1") == "glm-5"
    assert canonical_model("glm-5-chutes") == "glm-5"
    assert canonical_model("openrouter/z-ai/glm-5") == "glm-5"


def test_canonical_model_unknown():
    assert canonical_model("some-new-model") == "some-new-model"


def test_format_rules_report_with_data():
    rules = {
        "coding": {
            "models": ["model-a", "model-b"],
            "win_rates": {"model-a": 0.7, "model-b": 0.5},
            "total_battles": 100,
        }
    }
    report = format_rules_report(rules)
    assert "CODING" in report
    assert "model-a" in report
    assert "100 battles" in report


def test_format_rules_report_empty():
    report = format_rules_report({})
    assert "Total battles analyzed: 0" in report


def test_format_rules_report_warns_insufficient_data():
    rules = {
        "creative": {
            "models": ["model-a"],
            "win_rates": {"model-a": 1.0},
            "total_battles": 5,  # Below MIN_BATTLES_RELIABLE
        }
    }
    report = format_rules_report(rules)
    assert "WARNING" in report
    assert "insufficient" in report.lower()
    assert "creative" in report


def test_min_battles_constant():
    assert MIN_BATTLES_RELIABLE >= 20
