import unittest
from unittest.mock import patch, MagicMock

from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig
from llm_consortium.strategies.base import ConsortiumStrategy
from llm_consortium.orchestrator import IterationContext

class MockCachingStrategy(ConsortiumStrategy):
    def select_models(self, available_models, current_prompt, iteration):
        return {"model1": 1}

    def process_responses(self, successful_responses, iteration):
        return successful_responses

    def prepare_iteration_prompt(self, model_id, instance, original_prompt, iteration):
        return "PREPARED PROMPT BY STRATEGY"

class TestIterationPrompting(unittest.TestCase):
    def setUp(self):
        self.config = ConsortiumConfig(
            models={"model1": 1},
            confidence_threshold=0.8,
            max_iterations=2,
            minimum_iterations=1,
            manual_context=False
        )

    @patch('llm_consortium.orchestrator.save_consortium_run')
    @patch('llm_consortium.orchestrator.llm.get_model')
    @patch('llm_consortium.orchestrator.log_response')
    @patch('llm_consortium.orchestrator.save_consortium_member')
    @patch('llm_consortium.orchestrator.save_arbiter_decision')
    def test_automatic_delegates_prompt_construction(
        self, mock_save_decision, mock_save_member, mock_log, mock_get_model, mock_save_run
    ):
        mock_model = MagicMock()
        mock_conversation = MagicMock()
        mock_response = MagicMock()
        
        mock_response.text.return_value = "<confidence>0.9</confidence> Ok"
        mock_conversation.prompt.return_value = mock_response
        mock_model.conversation.return_value = mock_conversation
        mock_get_model.return_value = mock_model

        orchestrator = ConsortiumOrchestrator(self.config)
        # Override the strategy with our mock
        orchestrator.strategy = MockCachingStrategy(orchestrator, {})
        
        # Inject some history so we enter the multiple-iteration code path
        # orchestrator._get_model_responses_automatic uses history for subsequent prompts
        orchestrator.iteration_history = [{"iteration": 1, "synthesis": {"synthesis": "prev"}}]

        prompt = "Original Prompt"
        tasks = [{"model_id": "model1", "instance": 0, "conversation": mock_conversation, "system_prompt": None}]
        selected = {"model1": 1}

        # Trigger the response gathering logic
        orchestrator._get_model_responses_automatic(prompt, tasks, selected, 2)
        
        # We assert that the conversation.prompt was called with the string prepared by the strategy
        mock_conversation.prompt.assert_called_with(
            "PREPARED PROMPT BY STRATEGY", system=None
        )

    @patch('llm_consortium.orchestrator.save_consortium_run')
    @patch('llm_consortium.orchestrator.llm.get_model')
    @patch('llm_consortium.orchestrator.log_response')
    @patch('llm_consortium.orchestrator.save_consortium_member')
    @patch('llm_consortium.orchestrator.save_arbiter_decision')
    def test_manual_delegates_prompt_construction(
        self, mock_save_decision, mock_save_member, mock_log, mock_get_model, mock_save_run
    ):
        mock_model = MagicMock()
        mock_response = MagicMock()
        
        mock_response.text.return_value = "<confidence>0.9</confidence> Ok!"
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        self.config.manual_context = True
        orchestrator = ConsortiumOrchestrator(self.config)
        orchestrator.strategy = MockCachingStrategy(orchestrator, {})

        orchestrator.iteration_history = [{"iteration": 1, "synthesis": {"synthesis": "prev"}}]
        
        # Attempt manual prompt
        orchestrator._get_single_model_response_manual("model1", "Original Prompt", instance=0, iteration=2)
        
        mock_model.prompt.assert_called_with(
            "PREPARED PROMPT BY STRATEGY", system=None
        )

if __name__ == '__main__':
    unittest.main()
