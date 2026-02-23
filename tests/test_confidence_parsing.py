import unittest
from unittest.mock import MagicMock
import re
import llm_consortium
from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig

class TestConfidenceParsing(unittest.TestCase):
    def setUp(self):
        config = ConsortiumConfig(
            models={"model1": 1, "model2": 1},
            confidence_threshold=0.8,
            max_iterations=3,
            arbiter="arbiter_model"
        )
        self.orchestrator = ConsortiumOrchestrator(config=config)
    
    def test_parse_confidence_value_with_tag(self):
        # Test with <confidence> tag
        text = "Some text <confidence>0.85</confidence> more text"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.85)
    
    def test_parse_confidence_value_with_percentage(self):
        # Test with percentage in "confidence:" format
        text = "confidence: 75%"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.75)
    
    def test_parse_confidence_value_with_decimal(self):
        # Test with decimal in "confidence:" format
        text = "confidence: 0.92"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.92)
    
    def test_parse_confidence_value_no_value(self):
        # Test with no confidence value — should return default
        text = "No confidence value present"
        result = self.orchestrator._parse_confidence_value(text, 0.4)
        self.assertEqual(result, 0.4)  # Should use provided default
    
    def test_parse_confidence_value_multiple_matches(self):
        # Test with multiple confidence values, should take the XML tag first
        text = "<confidence>0.85</confidence> and later <confidence>0.75</confidence>"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.85)
    
    def test_parse_confidence_value_invalid_value(self):
        # Test with invalid confidence value in XML tag
        text = "<confidence>invalid</confidence>"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.5)  # Should use provided default
    
    def test_parse_confidence_value_over_100(self):
        # Test with value > 1 (percentage-like) — should normalize to 0-1
        text = "<confidence>85</confidence>"
        result = self.orchestrator._parse_confidence_value(text, 0.5)
        self.assertEqual(result, 0.85)
    
    def test_parse_confidence_value_default_zero(self):
        # Test default value when no default specified (should be 0.0)
        text = "Nothing here"
        result = self.orchestrator._parse_confidence_value(text)
        self.assertEqual(result, 0.0)

if __name__ == '__main__':
    unittest.main()
