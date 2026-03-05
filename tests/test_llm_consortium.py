import unittest
from unittest.mock import patch, MagicMock, call
import uuid
from llm_consortium import (
    ConsortiumOrchestrator, 
    DatabaseConnection, 
    ConsortiumConfig,
    IterationContext
)

# Using a simplified config for tests
TEST_CONFIG = ConsortiumConfig(
    models={"model1": 1, "model2": 1},
    confidence_threshold=0.8,
    max_iterations=3,
    minimum_iterations=1,
    arbiter="arbiter_model",
    system_prompt="Test System Prompt",
    manual_context=True  # Use manual context to avoid needing real llm conversations
)

class TestConsortiumOrchestrator(unittest.TestCase):
    def setUp(self):
        # Patch the save_consortium_run to avoid DB errors during orchestration
        with patch('llm_consortium.orchestrator.save_consortium_run'):
            self.orchestrator = ConsortiumOrchestrator(config=TEST_CONFIG)

    @patch('llm_consortium.orchestrator.llm.get_model')
    @patch('llm_consortium.orchestrator.save_consortium_member')
    def test_get_model_response(self, mock_save_member, mock_get_model):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text.return_value = "<confidence>0.75</confidence> Test response text"
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        # orchestrate is sync; test the manual single model response
        # Passing an instance variable to mimic the behavior in _get_model_responses_manual
        result = self.orchestrator._get_single_model_response_manual(
            "model1", "Test prompt", instance=0, iteration=1
        )
        self.assertEqual(result["model"], "model1")
        # Ensure we check based on what our mock returns
        self.assertEqual(result["response"], mock_response.text.return_value)
        self.assertEqual(result["confidence"], 0.75)

    @patch('llm_consortium.orchestrator.llm.get_model')
    @patch('llm_consortium.orchestrator.log_response')
    @patch('llm_consortium.orchestrator.save_consortium_member')
    @patch('llm_consortium.orchestrator.save_arbiter_decision')
    def test_synthesize_responses(self, mock_save_decision, mock_save_member, mock_log_response, mock_get_model):
        mock_arbiter = MagicMock()
        mock_response = MagicMock()
        mock_response.text.return_value = """
        <synthesis_output>
            <synthesis>Synthesized response</synthesis>
            <confidence>0.85</confidence>
            <analysis>Analysis of responses</analysis>
            <dissent>Dissenting views</dissent>
            <needs_iteration>false</needs_iteration>
            <refinement_areas>
                <area>Area 1</area>
                <area>Area 2</area>
            </refinement_areas>
        </synthesis_output>
        """
        mock_arbiter.prompt.return_value = mock_response
        mock_get_model.return_value = mock_arbiter

        responses = [
            {"model": "model1", "response": "Response 1", "confidence": 0.7, "id": 1},
            {"model": "model2", "response": "Response 2", "confidence": 0.8, "id": 2}
        ]
        self.orchestrator.iteration_history = []
        self.orchestrator._conversation_history = ""

        result = self.orchestrator._synthesize_responses_manual(
            "Original prompt", responses, [], 1
        )

        self.assertEqual(result["synthesis"], "Synthesized response")
        self.assertEqual(result["confidence"], 0.85)
        self.assertEqual(result["analysis"], "Analysis of responses")
        self.assertFalse(result["needs_iteration"])

    @patch.object(ConsortiumOrchestrator, '_get_model_responses_manual')
    @patch.object(ConsortiumOrchestrator, '_synthesize_responses_manual')
    @patch('llm_consortium.orchestrator.save_consortium_run')
    def test_orchestrate_single_iteration_success(self, mock_save_run, mock_synthesize, mock_get_responses):
        mock_get_responses.return_value = [
            {"model": "model1", "response": "Response 1", "confidence": 0.7, "id": 1},
            {"model": "model2", "response": "Response 2", "confidence": 0.8, "id": 2}
        ]
        mock_synthesize.return_value = {
            "synthesis": "Final synthesis", 
            "confidence": 0.9,
            "analysis": "Final analysis", 
            "dissent": "Final dissent",
            "needs_iteration": False, 
            "refinement_areas": [],
            "raw_arbiter_response": "raw text"
        }

        # orchestrate is sync
        result = self.orchestrator.orchestrate("Test prompt")

        mock_get_responses.assert_called_once()
        mock_synthesize.assert_called_once()
        self.assertEqual(result["synthesis"]["confidence"], 0.9)
        self.assertEqual(result["metadata"]["total_iterations"], 1)

    @patch.object(ConsortiumOrchestrator, '_get_model_responses_manual')
    @patch.object(ConsortiumOrchestrator, '_synthesize_responses_manual')
    @patch('llm_consortium.orchestrator.save_consortium_run')
    def test_orchestrate_with_history(self, mock_save_run, mock_synthesize, mock_get_responses):
        mock_get_responses.return_value = [
            {"model": "model1", "response": "Response 1", "confidence": 0.7, "id": 1},
            {"model": "model2", "response": "Response 2", "confidence": 0.8, "id": 2}
        ]
        mock_synthesize.return_value = {
            "synthesis": "Final synthesis with history", 
            "confidence": 0.95,
            "analysis": "Final analysis", 
            "dissent": "Final dissent",
            "needs_iteration": False, 
            "refinement_areas": [],
            "raw_arbiter_response": "raw text"
        }

        history = "Human: Previous question\nAssistant: Previous answer"
        current_prompt = "Follow-up question"

        # orchestrate is sync
        result = self.orchestrator.orchestrate(current_prompt, conversation_history=history)

        mock_get_responses.assert_called_once()
        mock_synthesize.assert_called_once()
        self.assertEqual(result["synthesis"]["confidence"], 0.95)
        self.assertEqual(result["metadata"]["total_iterations"], 1)
        self.assertEqual(result["original_prompt"], current_prompt)


class TestDatabaseConnection(unittest.TestCase):
    @patch('llm_consortium.db.sqlite_utils.Database')
    def test_get_connection(self, mock_database):
        # Ensure thread local storage is clean for this test
        if hasattr(DatabaseConnection._thread_local, 'db'):
            del DatabaseConnection._thread_local.db

        connection1 = DatabaseConnection.get_connection()
        connection2 = DatabaseConnection.get_connection()

        self.assertIs(connection1, connection2)
        mock_database.assert_called_once()
