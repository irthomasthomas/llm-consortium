import unittest
from unittest.mock import MagicMock
from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig

class TestArbiterParsing(unittest.TestCase):
    def setUp(self):
        config = ConsortiumConfig(
            models={"model1": 1, "model2": 1},
            confidence_threshold=0.8,
            max_iterations=3,
            arbiter="arbiter_model"
        )
        self.orchestrator = ConsortiumOrchestrator(config=config)
    
    def test_parse_arbiter_response_complete(self):
        # Test with a complete, well-formed response
        text = """
        <synthesis_output>
            <synthesis>This is the synthesized response</synthesis>
            <confidence>0.85</confidence>
            <analysis>Analysis of the model responses</analysis>
            <dissent>Points of disagreement</dissent>
            <needs_iteration>false</needs_iteration>
            <refinement_areas>
                <area>Area 1</area>
                <area>Area 2</area>
            </refinement_areas>
        </synthesis_output>
        """
        
        result = self.orchestrator._parse_arbiter_response(text)
        
        self.assertEqual(result["synthesis"], "This is the synthesized response")
        self.assertEqual(result["confidence"], 0.85)
        self.assertEqual(result["analysis"], "Analysis of the model responses")
        self.assertEqual(result["dissent"], "Points of disagreement")
        self.assertFalse(result["needs_iteration"])
        self.assertEqual(result["refinement_areas"], ["Area 1", "Area 2"])
    
    def test_parse_arbiter_response_true_iteration(self):
        # Test with needs_iteration set to true
        text = """
        <synthesis_output>
            <synthesis>This is the synthesized response</synthesis>
            <confidence>0.65</confidence>
            <analysis>Analysis of the model responses</analysis>
            <dissent>Points of disagreement</dissent>
            <needs_iteration>true</needs_iteration>
            <refinement_areas>
                <area>Area 1</area>
                <area>Area 2</area>
            </refinement_areas>
        </synthesis_output>
        """
        
        result = self.orchestrator._parse_arbiter_response(text)
        
        self.assertEqual(result["confidence"], 0.65)
        self.assertTrue(result["needs_iteration"])
    
    def test_parse_arbiter_response_missing_elements(self):
        # Test with missing elements
        text = """
        <synthesis_output>
            <synthesis>This is the synthesized response</synthesis>
            <confidence>0.75</confidence>
        </synthesis_output>
        """
        
        result = self.orchestrator._parse_arbiter_response(text)
        
        self.assertEqual(result["synthesis"], "This is the synthesized response")
        self.assertEqual(result["confidence"], 0.75)
        self.assertEqual(result["analysis"], "")  # Default empty string
        self.assertEqual(result["dissent"], "")  # Default empty string
        self.assertFalse(result["needs_iteration"])  # Default False
        self.assertEqual(result["refinement_areas"], [])  # Default empty list
    
    def test_parse_arbiter_response_malformed(self):
        # Test with malformed XML
        text = """
        <synthesis_output>
            <synthesis>This is the synthesized response
            <confidence>0.75
        </synthesis_output>
        """
        
        # Should handle the error and return default values
        result = self.orchestrator._parse_arbiter_response(text)
        
        # Malformed tags won't match regex, so defaults are used
        self.assertEqual(result["synthesis"], text)  # Full text as fallback synthesis
        self.assertEqual(result["confidence"], 0.0)  # Default confidence
        self.assertEqual(result["analysis"], "")
        self.assertEqual(result["dissent"], "")
        self.assertFalse(result["needs_iteration"])
        self.assertEqual(result["refinement_areas"], [])
    
    def test_parse_arbiter_response_is_final_iteration(self):
        # Test with is_final_iteration=True
        # Note: current implementation does NOT override needs_iteration based on is_final_iteration
        text = """
        <synthesis_output>
            <synthesis>This is the synthesized response</synthesis>
            <confidence>0.65</confidence>
            <needs_iteration>true</needs_iteration>
        </synthesis_output>
        """
        
        result = self.orchestrator._parse_arbiter_response(text, is_final_iteration=True)
        
        self.assertEqual(result["confidence"], 0.65)
        # is_final_iteration is accepted but does not override the parsed value
        self.assertTrue(result["needs_iteration"])

if __name__ == '__main__':
    unittest.main()
