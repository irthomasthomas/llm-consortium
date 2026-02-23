import unittest
from llm_consortium import parse_models

class TestModelParsing(unittest.TestCase):
    def test_parse_models_with_counts(self):
        # Test model specifications with explicit counts
        models = ["model1:2", "model2:3", "model3:1"]
        default_count = 1
        
        result = parse_models(models, default_count)
        
        self.assertEqual(result, {
            "model1": 2,
            "model2": 3,
            "model3": 1
        })
        
    def test_parse_models_with_default_count(self):
        # Test model specifications without counts
        models = ["model1", "model2", "model3"]
        default_count = 2
        
        result = parse_models(models, default_count)
        
        self.assertEqual(result, {
            "model1": 2,
            "model2": 2,
            "model3": 2
        })
        
    def test_parse_models_mixed(self):
        # Test mix of models with and without counts
        models = ["model1:3", "model2", "model3:1"]
        default_count = 2
        
        result = parse_models(models, default_count)
        
        self.assertEqual(result, {
            "model1": 3,
            "model2": 2,
            "model3": 1
        })
        
    def test_parse_models_empty(self):
        # Test with empty model list
        models = []
        default_count = 1
        
        result = parse_models(models, default_count)
        
        self.assertEqual(result, {})
        
    def test_parse_models_invalid_count(self):
        # Test with invalid count format — current implementation raises ValueError
        models = ["model1:invalid"]
        default_count = 1
        
        with self.assertRaises(ValueError):
            parse_models(models, default_count)
        
    def test_parse_models_zero_count(self):
        # Test with zero count
        models = ["model1:0"]
        default_count = 1
        
        # Zero count should be preserved
        result = parse_models(models, default_count)
        
        self.assertEqual(result, {"model1": 0})

if __name__ == '__main__':
    unittest.main()
