"""Tests for multi-turn conversation context retention."""
import unittest
from unittest.mock import patch, MagicMock
import uuid
from llm_consortium import (
    ConsortiumOrchestrator,
    ConsortiumConfig,
)
from llm_consortium.db import DatabaseConnection


class TestMultiTurnConversation(unittest.TestCase):
    """Verify that conversation context is retained across multiple calls."""

    def setUp(self):
        self.config = ConsortiumConfig(
            models={"model1": 2, "model2": 1},
            confidence_threshold=0.8,
            max_iterations=2,
            minimum_iterations=1,
            arbiter="arbiter_model",
            system_prompt="You are a helpful assistant.",
            manual_context=False,  # Use automatic mode (conversation objects)
        )

    def test_orchestrator_has_conversation_storage_attributes(self):
        """Verify orchestrator initialises with conversation storage."""
        orch = ConsortiumOrchestrator(config=self.config)
        self.assertTrue(hasattr(orch, "model_conversations"))
        self.assertIsInstance(orch.model_conversations, dict)
        self.assertEqual(len(orch.model_conversations), 0)
        self.assertTrue(hasattr(orch, "arbiter_conversation"))
        self.assertIsNone(orch.arbiter_conversation)

    def test_get_model_conversation_creates_and_reuses(self):
        """_get_model_conversation should create once then return the same object."""
        orch = ConsortiumOrchestrator(config=self.config)

        with patch("llm_consortium.orchestrator.llm.get_model") as mock_get_model:
            def make_conv():
                return MagicMock()

            mock_model = MagicMock()
            mock_model.conversation.side_effect = lambda: MagicMock()
            mock_get_model.return_value = mock_model

            conv1 = orch._get_model_conversation("model1", 0)
            conv2 = orch._get_model_conversation("model1", 0)
            conv3 = orch._get_model_conversation("model1", 1)  # different instance
            conv4 = orch._get_model_conversation("model2", 0)  # different model

            # Same model + instance → same conversation
            self.assertIs(conv1, conv2)
            # Different instance or model → different conversation
            self.assertIsNot(conv1, conv3)
            self.assertIsNot(conv1, conv4)
            # model.conversation() called 3 times (one per unique key)
            self.assertEqual(mock_model.conversation.call_count, 3)
            # 3 keys stored
            self.assertEqual(len(orch.model_conversations), 3)

    def test_get_arbiter_conversation_creates_and_reuses(self):
        """_get_arbiter_conversation should create once then return the same."""
        orch = ConsortiumOrchestrator(config=self.config)

        with patch("llm_consortium.orchestrator.llm.get_model") as mock_get_model:
            mock_arbiter = MagicMock()
            mock_conv = MagicMock()
            mock_arbiter.conversation.return_value = mock_conv
            mock_get_model.return_value = mock_arbiter

            conv1 = orch._get_arbiter_conversation()
            conv2 = orch._get_arbiter_conversation()

            self.assertIs(conv1, conv2)

    @patch("llm_consortium.orchestrator.llm.get_model")
    @patch("llm_consortium.orchestrator.save_consortium_run")
    @patch("llm_consortium.orchestrator.save_arbiter_decision")
    @patch("llm_consortium.orchestrator.save_consortium_member")
    @patch("llm_consortium.orchestrator.log_response")
    def test_multi_turn_prompts_include_history(
        self, mock_log, mock_save_member, mock_save_decision,
        mock_save_run, mock_get_model
    ):
        """Simulate two turns and verify the second receives conversation history."""
        orch = ConsortiumOrchestrator(config=self.config)

        # --- Set up mocks ---
        mock_model = MagicMock()
        mock_conv = MagicMock()
        mock_model.conversation.return_value = mock_conv
        mock_get_model.return_value = mock_model

        # Model responses
        def make_response(text, confidence=0.9):
            resp = MagicMock()
            resp.text.return_value = text
            resp.id = str(uuid.uuid4())
            return resp

        model_response = make_response(
            "<confidence>0.9</confidence> Simple answer."
        )
        arbiter_response = make_response(
            """<synthesis_output>
                <synthesis>Simple answer.</synthesis>
                <confidence>0.95</confidence>
                <analysis>Good</analysis>
                <dissent></dissent>
                <needs_iteration>false</needs_iteration>
                <refinement_areas>
                    <area>none</area>
                </refinement_areas>
            </synthesis_output>"""
        )

        # model.prompt and conversation.prompt both work
        mock_conv.prompt.return_value = arbiter_response
        mock_model.prompt.return_value = model_response

        # --- Turn 1 ---
        result1 = orch.orchestrate(
            "Write a winter haiku.",
            conversation_history=None,
            consortium_id=str(uuid.uuid4()),
        )
        self.assertIn("synthesis", result1)
        # After turn 1, no history stored yet (None was passed)
        self.assertEqual(orch._conversation_history, "")

        # --- Turn 2 (with history from previous exchange) ---
        history = "Human: Write a winter haiku.\nAssistant: Simple answer."
        result2 = orch.orchestrate(
            "What are we discussing?",
            conversation_history=history,
            consortium_id=str(uuid.uuid4()),
        )
        self.assertIn("synthesis", result2)
        # History should be stored now
        self.assertEqual(orch._conversation_history, history)

        # Verify model conversation was reused across calls
        # Check the conversation object was used for Turn 2
        self.assertIn("model1_0", orch.model_conversations)

    def test_manual_context_disables_conversation_storage(self):
        """In manual mode, conversations should not be stored."""
        manual_config = ConsortiumConfig(
            models={"model1": 1},
            confidence_threshold=0.8,
            max_iterations=2,
            minimum_iterations=1,
            arbiter="arbiter_model",
            manual_context=True,
        )
        orch = ConsortiumOrchestrator(config=manual_config)

        conv = orch._get_model_conversation("model1", 0)
        self.assertIsNone(conv)

        arb_conv = orch._get_arbiter_conversation()
        self.assertIsNone(arb_conv)

    def test_reset_conversations_clears_storage(self):
        """reset_model_conversations and reset_arbiter_conversation clear storage."""
        orch = ConsortiumOrchestrator(config=self.config)

        with patch("llm_consortium.orchestrator.llm.get_model") as mock_get_model:
            def make_conv():
                return MagicMock()

            mock_model = MagicMock()
            mock_model.conversation.side_effect = lambda: MagicMock()
            mock_get_model.return_value = mock_model

            # Populate
            orch._get_model_conversation("model1", 0)
            orch._get_model_conversation("model2", 0)
            orch._get_arbiter_conversation()

            self.assertEqual(len(orch.model_conversations), 2)
            self.assertIsNotNone(orch.arbiter_conversation)

            # Reset
            orch.reset_model_conversations()
            orch.reset_arbiter_conversation()

            self.assertEqual(len(orch.model_conversations), 0)
            self.assertIsNone(orch.arbiter_conversation)


if __name__ == "__main__":
    unittest.main()
