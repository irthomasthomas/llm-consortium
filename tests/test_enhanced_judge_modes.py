"""
Tests for enhanced judge modes: rank-cot parsing, per-model guidance,
and skip_intermediate_synthesis logic.
"""
import json
import unittest
from unittest.mock import MagicMock, patch
from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig


class TestRankCotParsing(unittest.TestCase):
    """Test parsing of rank-cot arbiter responses."""

    def setUp(self):
        config = ConsortiumConfig(
            models={"model1": 1, "model2": 1},
            confidence_threshold=0.8,
            max_iterations=3,
            arbiter="arbiter_model",
            judging_method="rank-cot"
        )
        self.orchestrator = ConsortiumOrchestrator(config=config)
        self.responses = [
            {"model": "model1", "instance": 0, "response": "Answer 1", "confidence": 0.7, "id": 100, "response_id": "r100"},
            {"model": "model2", "instance": 0, "response": "Answer 2", "confidence": 0.8, "id": 200, "response_id": "r200"},
        ]

    def test_parse_rank_cot_complete(self):
        text = json.dumps({
            "evaluation": [
                {"id": 100, "strengths": "Well-reasoned", "weaknesses": "Missing edge case"},
                {"id": 200, "strengths": "Complete answer", "weaknesses": "Verbose"},
            ],
            "analysis": "Model2 provided a more complete answer.",
            "dissent": "None significant.",
            "synthesis": "Answer 2",
            "confidence": 0.85,
            "refinement_areas": ["Edge cases"],
            "needs_iteration": False,
            "ranking": [200, 100],
            "model_guidance": {"model1_0": "Consider edge cases next time.",
                               "model2_0": "Good work, trim verbosity."},
        })
        result = self.orchestrator._parse_rank_cot_response(text, self.responses)

        self.assertEqual(result["synthesis"], "Answer 2")
        self.assertEqual(result["confidence"], 0.85)
        self.assertFalse(result["needs_iteration"])
        self.assertEqual(result["ranking"], [200, 100])
        self.assertEqual(result["chosen_response_id"], "r200")
        self.assertIn("evaluation", result)
        self.assertTrue(any("Well-reasoned" in str(e.get("strengths", "")) for e in result["evaluation"]))
        self.assertIn("model_guidance", result)
        self.assertEqual(result["model_guidance"]["model1_0"], "Consider edge cases next time.")
        self.assertEqual(result["model_guidance"]["model2_0"], "Good work, trim verbosity.")

    def test_parse_rank_cot_missing_evaluation(self):
        """rank-cot should still work without evaluation section."""
        text = json.dumps({
            "analysis": "Brief analysis.",
            "synthesis": "Answer 1",
            "confidence": 0.7,
            "needs_iteration": True,
            "ranking": [100, 200],
        })
        result = self.orchestrator._parse_rank_cot_response(text, self.responses)
        self.assertEqual(result["evaluation"], [])
        self.assertEqual(result["model_guidance"], {})
        self.assertTrue(result["needs_iteration"])

    def test_parse_rank_cot_missing_model_guidance(self):
        """rank-cot should work without model_guidance section."""
        text = json.dumps({
            "evaluation": [{"id": 100, "strengths": "Good", "weaknesses": "None"}],
            "synthesis": "Answer 1",
            "confidence": 0.9,
            "needs_iteration": False,
            "ranking": [100],
        })
        result = self.orchestrator._parse_rank_cot_response(text, self.responses)
        self.assertEqual(result["model_guidance"], {})


class TestSkipIntermediateSynthesis(unittest.TestCase):
    """Test skip_intermediate_synthesis config and prompt building."""

    def test_config_defaults(self):
        """New config fields should have correct defaults."""
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter"
        )
        self.assertFalse(config.skip_intermediate_synthesis)
        self.assertTrue(config.per_model_guidance)

    def test_config_enabled(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            skip_intermediate_synthesis=True,
            per_model_guidance=False
        )
        self.assertTrue(config.skip_intermediate_synthesis)
        self.assertFalse(config.per_model_guidance)

    def test_config_roundtrip(self):
        """Config should survive to_dict/from_dict roundtrip."""
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            skip_intermediate_synthesis=True,
            per_model_guidance=False
        )
        restored = ConsortiumConfig.from_dict(config.to_dict())
        self.assertTrue(restored.skip_intermediate_synthesis)
        self.assertFalse(restored.per_model_guidance)

    def test_skip_synthesis_prompt_intermediate(self):
        """On intermediate iterations, skip instruction should be appended."""
        config = ConsortiumConfig(
            models={"model1": 1, "model2": 1},
            arbiter="arbiter",
            max_iterations=3,
            skip_intermediate_synthesis=True
        )
        orch = ConsortiumOrchestrator(config=config)
        responses = [{"model": "m1", "instance": 0, "response": "r1", "id": 1, "response_id": "r1"}]

        prompt = orch._prepare_arbiter_prompt("test prompt", responses, [], iteration=1)
        self.assertIn("INTERMEDIATE", prompt)
        self.assertIn("DEFERRED", prompt.upper())

    def test_skip_synthesis_prompt_final_iteration(self):
        """On the last iteration, no skip instruction should be appended."""
        config = ConsortiumConfig(
            models={"model1": 1, "model2": 1},
            arbiter="arbiter",
            max_iterations=3,
            skip_intermediate_synthesis=True
        )
        orch = ConsortiumOrchestrator(config=config)
        responses = [{"model": "m1", "instance": 0, "response": "r1", "id": 1, "response_id": "r1"}]

        prompt = orch._prepare_arbiter_prompt("test prompt", responses, [], iteration=3)
        self.assertNotIn("INTERMEDIATE EVALUATION MODE", prompt)

    def test_skip_synthesis_disabled(self):
        """When skip_intermediate_synthesis is False, no skip instruction."""
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            max_iterations=3,
            skip_intermediate_synthesis=False
        )
        orch = ConsortiumOrchestrator(config=config)
        responses = [{"model": "m1", "instance": 0, "response": "r1", "id": 1, "response_id": "r1"}]

        prompt = orch._prepare_arbiter_prompt("test prompt", responses, [], iteration=1)
        self.assertNotIn("INTERMEDIATE EVALUATION MODE", prompt)

    def test_build_skip_synthesis_instruction_per_model(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            per_model_guidance=True
        )
        orch = ConsortiumOrchestrator(config=config)
        instruction = orch._build_skip_synthesis_instruction([])
        self.assertIn("model_guidance", instruction)

    def test_build_skip_synthesis_instruction_shared(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            per_model_guidance=False
        )
        orch = ConsortiumOrchestrator(config=config)
        instruction = orch._build_skip_synthesis_instruction([])
        self.assertNotIn("model_guidance", instruction)


class TestRankCotConfigNormalization(unittest.TestCase):
    """Test that rank-cot judging method is properly normalized."""

    def test_rank_cot_preserved(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            judging_method="rank-cot"
        )
        self.assertEqual(config.judging_method, "rank-cot")

    def test_rank_cot_uppercase(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            judging_method="Rank-COT"
        )
        self.assertEqual(config.judging_method, "rank-cot")

    def test_rank_cot_space(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            judging_method="rank cot"
        )
        self.assertEqual(config.judging_method, "rank-cot")

    def test_default_normalization(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            judging_method="DEFAULT"
        )
        self.assertEqual(config.judging_method, "default")


class TestDeferredSynthesisHandling(unittest.TestCase):
    """Test that deferred synthesis ([DEFERRED]) is handled correctly."""

    def setUp(self):
        config = ConsortiumConfig(
            models={"model1": 1},
            arbiter="arbiter",
            max_iterations=2,
            skip_intermediate_synthesis=True
        )
        self.orchestrator = ConsortiumOrchestrator(config=config)

    def test_model_guidance_in_arbiter_response(self):
        """_parse_arbiter_response should also parse model_guidance."""
        text = json.dumps({
            "synthesis": "[DEFERRED]",
            "confidence": 0.6,
            "needs_iteration": True,
            "ranking": [100],
            "model_guidance": {"model1_0": "Improve accuracy."},
        })
        result = self.orchestrator._parse_arbiter_response(text)
        self.assertEqual(result["synthesis"], "[DEFERRED]")
        self.assertTrue(result["needs_iteration"])
        self.assertEqual(result["model_guidance"]["model1_0"], "Improve accuracy.")


if __name__ == "__main__":
    unittest.main()
