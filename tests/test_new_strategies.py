"""Tests for ring_ling and cascade strategies."""
import pytest
from llm_consortium.strategies.ring_ling import RingLingStrategy, extract_reasoning
from llm_consortium.strategies.cascade import CascadeStrategy


def test_ring_ling_requires_reasoning_model():
    with pytest.raises(ValueError, match="reasoning_model"):
        RingLingStrategy(orchestrator=None, params={"answer_model": "test"})


def test_ring_ling_requires_answer_model():
    with pytest.raises(ValueError, match="answer_model"):
        RingLingStrategy(orchestrator=None, params={"reasoning_model": "test"})


def test_ring_ling_valid_params():
    strat = RingLingStrategy(orchestrator=None, params={
        "reasoning_model": "ring-2.6", "answer_model": "ling-2.6"
    })
    assert strat.reasoning_model == "ring-2.6"
    assert strat.answer_model == "ling-2.6"


def test_ring_ling_select_models_iteration1():
    strat = RingLingStrategy(orchestrator=None, params={
        "reasoning_model": "ring-2.6", "answer_model": "ling-2.6"
    })
    strat.initialize_state()
    selected = strat.select_models({"ling-2.6": 1, "ring-2.6": 1}, "test", 1)
    assert "ring-2.6" in selected
    assert "ling-2.6" not in selected


def test_ring_ling_select_models_iteration2():
    strat = RingLingStrategy(orchestrator=None, params={
        "reasoning_model": "ring-2.6", "answer_model": "ling-2.6"
    })
    strat.initialize_state()
    strat.iteration_state["reasoning"] = "Some reasoning here"
    selected = strat.select_models({"ling-2.6": 1, "ring-2.6": 1}, "test", 2)
    assert "ling-2.6" in selected
    assert "ring-2.6" not in selected


def test_extract_reasoning_think_tags():
    text = "<think>Step 1: Consider\nStep 2: Therefore</think>The answer is 42."
    reasoning = extract_reasoning(text)
    assert "Step 1" in reasoning
    assert "Step 2" in reasoning


def test_cascade_requires_tiers():
    with pytest.raises(ValueError, match="tiers"):
        CascadeStrategy(orchestrator=None, params={})


def test_cascade_valid_params():
    strat = CascadeStrategy(orchestrator=None, params={
        "tiers": [["cheap-model"], ["strong-model"]]
    })
    assert len(strat.tiers) == 2


def test_cascade_starts_at_tier0():
    strat = CascadeStrategy(orchestrator=None, params={
        "tiers": [["model-a"], ["model-b"]]
    })
    strat.initialize_state()
    selected = strat.select_models({"model-a": 1, "model-b": 1}, "test", 1)
    assert "model-a" in selected
    assert "model-b" not in selected


def test_cascade_escalation():
    strat = CascadeStrategy(orchestrator=None, params={
        "tiers": [["model-a"], ["model-b"]],
        "error_threshold": 1
    })
    strat.initialize_state()
    
    # Simulate an error
    class MockContext:
        synthesis = {"confidence": 0.9}
        model_responses = [{"error": "timeout"}]
    
    strat.update_state(MockContext())
    assert strat.iteration_state["current_tier"] == 1
    
    # Next selection should use tier 1
    selected = strat.select_models({"model-a": 1, "model-b": 1}, "test", 2)
    assert "model-b" in selected
    assert "model-a" not in selected
