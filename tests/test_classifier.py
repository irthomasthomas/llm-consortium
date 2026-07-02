"""Tests for the task classifier module."""
import pytest
from llm_consortium.classifier.regex_rules import classify_prompt, get_routing_decision
from llm_consortium.classifier.tfidf import TFIDFClassifier


@pytest.mark.parametrize("prompt,expected", [
    ("Write a Python function to compute fibonacci numbers", "coding"),
    ("Debug this JavaScript null reference error", "coding"),
    ("Create a SQL query to find duplicates", "coding"),
    ("What is the capital of France?", "factual"),
    ("Who invented the telephone?", "factual"),
    ("Calculate the derivative of x^3 + 2x", "math"),
    ("What is 15% of 240?", "math"),
    ("Analyze the trade-offs between microservices and monoliths", "reasoning"),
    ("If all roses are flowers and some fade quickly, do all roses fade?", "reasoning"),
    ("Write a story about a time traveler", "creative"),
    ("Write a haiku about autumn", "creative"),
    ("How to configure nginx reverse proxy", "sysadmin"),
    ("Set up a cron job for daily backups", "sysadmin"),
])
def test_classify_prompt_categories(prompt, expected):
    result = classify_prompt(prompt)
    assert result["category"] == expected, f"Expected {expected}, got {result['category']} for: {prompt}"


def test_classify_prompt_confidence_range():
    result = classify_prompt("Write a Python function")
    assert 0.0 <= result["confidence"] <= 1.0


def test_classify_prompt_general_for_unknown():
    result = classify_prompt("hello world")
    assert result["category"] == "general"
    assert result["confidence"] == 0.0


def test_get_routing_decision_known_category():
    decision = get_routing_decision("coding")
    assert "models" in decision
    assert "strategy" in decision
    assert len(decision["models"]) >= 1


def test_get_routing_decision_unknown_category():
    decision = get_routing_decision("nonexistent")
    assert "models" in decision
    assert decision == get_routing_decision("general")


def test_tfidf_classifier_categories():
    clf = TFIDFClassifier()
    result = clf.classify("Write a Python function to sort a list")
    assert result["category"] == "coding"
    assert result["method"] == "tfidf"


def test_tfidf_classifier_confidence():
    clf = TFIDFClassifier()
    result = clf.classify("Calculate the integral of sin(x)")
    assert 0.0 <= result["confidence"] <= 1.0
