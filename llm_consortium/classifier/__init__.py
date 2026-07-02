"""
Task classification for llm-consortium.

Provides classify() that determines prompt category using a fallback chain:
  1. Weighted regex patterns (fast, deterministic, no deps)
  2. TF-IDF similarity (pure Python, no sklearn needed)

This enables cost-aware routing: simple prompts use one model,
complex prompts use the full consortium.
"""
from .regex_rules import classify_prompt, get_routing_decision, PATTERNS, DEFAULT_ROUTING_RULES
from .tfidf import TFIDFClassifier

def classify(prompt: str, method: str = "auto") -> dict:
    """
    Classify a prompt into a task category.
    Returns: {category, confidence, method, scores, routing}
    """
    result = {"category": "general", "confidence": 0.0, "method": "none", "scores": {}}

    if method in ("regex", "auto"):
        result = classify_prompt(prompt)
        if result["confidence"] >= 0.15:
            result["routing"] = get_routing_decision(result["category"])
            return result

    if method in ("tfidf", "auto"):
        try:
            tfidf = TFIDFClassifier()
            tfidf_result = tfidf.classify(prompt)
            if tfidf_result["confidence"] > result.get("confidence", 0):
                result = tfidf_result
        except Exception:
            pass

    result["routing"] = get_routing_decision(result.get("category", "general"))
    return result

__all__ = ["classify", "classify_prompt", "get_routing_decision", "PATTERNS", "DEFAULT_ROUTING_RULES", "TFIDFClassifier"]
