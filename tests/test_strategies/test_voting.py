"""Tests for the VotingStrategy."""

import pytest
from unittest.mock import Mock
from llm_consortium.strategies.voting import VotingStrategy
from llm_consortium import IterationContext


class TestVotingStrategy:
    """Test cases for VotingStrategy."""
    
    def test_init_with_default_params(self):
        """Test initialization with default parameters."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        
        assert strategy.similarity_threshold == 0.5
        assert strategy.answer_length == 100
        assert strategy.require_majority is False
        assert strategy.fallback_to_all is True
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        mock_orchestrator = Mock()
        params = {
            'similarity_threshold': 0.8,
            'answer_length': 50,
            'require_majority': True,
            'fallback_to_all': False
        }
        strategy = VotingStrategy(mock_orchestrator, params)
        
        assert strategy.similarity_threshold == 0.8
        assert strategy.answer_length == 50
        assert strategy.require_majority is True
        assert strategy.fallback_to_all is False
    
    def test_validate_params_invalid_threshold(self):
        """Test validation fails with invalid threshold."""
        mock_orchestrator = Mock()
        with pytest.raises(ValueError, match="similarity_threshold must be between 0 and 1"):
            VotingStrategy(mock_orchestrator, {'similarity_threshold': 1.5})
    
    def test_validate_params_invalid_length(self):
        """Test validation fails with invalid answer length."""
        mock_orchestrator = Mock()
        with pytest.raises(ValueError, match="answer_length must be at least 10"):
            VotingStrategy(mock_orchestrator, {'answer_length': 5})
    
    def test_initialize_state(self):
        """Test state initialization."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        strategy.initialize_state()
        
        assert strategy.iteration_state['voting_history'] == []
        assert strategy.iteration_state['consensus_count'] == 0
        assert strategy.iteration_state['no_consensus_count'] == 0
    
    def test_select_models_returns_all(self):
        """Test that select_models returns all available models."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        
        available = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        selected = strategy.select_models(available, "test", 1)
        
        assert selected == available
    
    def test_calculate_similarity(self):
        """Test similarity calculation."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        
        # Identical texts
        sim = strategy._calculate_similarity("hello world", "hello world")
        assert sim == 1.0
        
        # Completely different texts
        sim = strategy._calculate_similarity("hello", "goodbye")
        assert sim < 0.5
        
        # Similar texts
        sim = strategy._calculate_similarity("The answer is 42", "The answer is 42!")
        assert sim > 0.9
    
    def test_group_similar_responses(self):
        """Test grouping of similar responses."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator, {'answer_length': 20, 'similarity_threshold': 0.7})
        
        responses = [
            {'model': 'gpt-4', 'response': 'The capital of France is Paris'},
            {'model': 'claude', 'response': 'The capital of France is Paris!'},
            {'model': 'gemini', 'response': 'Paris is the capital of France'},
            {'model': 'llama', 'response': 'Berlin is the capital of Germany'}
        ]
        
        groups = strategy._group_similar_responses(responses)
        
        # Should have 2 groups: one for Paris answers, one for Berlin
        assert len(groups) == 2
        # First group should have 3 Paris answers
        assert len(groups[0]) == 3
        # Second group should have 1 Berlin answer
        assert len(groups[1]) == 1
    
    def test_process_responses_single_response(self):
        """Test processing with single response."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        strategy.initialize_state()
        
        responses = [{'model': 'gpt-4', 'response': 'Single answer'}]
        result = strategy.process_responses(responses, 1)
        
        assert result == responses
        assert result[0]['voting_selected'] is True
        assert result[0]['voting_group_size'] == 1
        assert result[0]['voting_total'] == 1
    
    def test_process_responses_with_consensus(self):
        """Test processing when consensus is found."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator, {'answer_length': 20, 'similarity_threshold': 0.7})
        strategy.initialize_state()
        
        responses = [
            {'model': 'gpt-4', 'response': 'The answer is forty-two'},
            {'model': 'claude', 'response': 'The answer is forty two!'},
            {'model': 'gemini': 'response': 'Completely different response here'}
        ]
        
        result = strategy.process_responses(responses, 1)
        
        # Should return the consensus group (first two responses)
        assert len(result) == 2
        assert all(r['voting_selected'] for r in result)
        assert all(r['voting_group_size'] == 2 for r in result)
        assert all(r['voting_total'] == 3 for r in result)
        
        # Check state updated
        assert strategy.iteration_state['consensus_count'] == 1
        assert len(strategy.iteration_state['voting_history']) == 1
    
    def test_process_responses_require_majority(self):
        """Test processing with majority requirement."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator, {
            'answer_length': 20,
            'similarity_threshold': 0.7,
            'require_majority': True,
            'fallback_to_all': True
        })
        strategy.initialize_state()
        
        # 2 out of 3 agree - that's a majority
        responses = [
            {'model': 'gpt-4', 'response': 'The answer is forty-two'},
            {'model': 'claude', 'response': 'The answer is forty two!'},
            {'model': 'gemini', 'response': 'Completely different response here'}
        ]
        
        result = strategy.process_responses(responses, 1)
        
        # Should return the majority group
        assert len(result) == 2
        assert strategy.iteration_state['consensus_count'] == 1
    
    def test_process_responses_no_majority(self):
        """Test processing when no majority exists."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator, {
            'answer_length': 20,
            'require_majority': True,
            'fallback_to_all': True
        })
        strategy.initialize_state()
        
        # All different answers - no majority
        responses = [
            {'model': 'gpt-4', 'response': 'First unique answer'},
            {'model': 'claude', 'response': 'Second unique answer'},
            {'model': 'gemini', 'response': 'Third unique answer'}
        ]
        
        result = strategy.process_responses(responses, 1)
        
        # Should return all responses due to fallback
        assert len(result) == 3
        assert all(not r['voting_selected'] for r in result)
        assert strategy.iteration_state['no_consensus_count'] == 1
    
    def test_process_responses_no_fallback(self):
        """Test processing without fallback when no consensus."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator, {
            'require_majority': True,
            'fallback_to_all': False
        })
        strategy.initialize_state()
        
        responses = [
            {'model': 'gpt-4', 'response': 'First unique answer'},
            {'model': 'claude', 'response': 'Second unique answer'}
        ]
        
        result = strategy.process_responses(responses, 1)
        
        # Should return empty list
        assert result == []
        assert strategy.iteration_state['no_consensus_count'] == 1
    
    def test_update_state(self):
        """Test state update after iteration."""
        mock_orchestrator = Mock()
        strategy = VotingStrategy(mock_orchestrator)
        strategy.initialize_state()
        
        # Simulate some voting history
        strategy.iteration_state['consensus_count'] = 2
        strategy.iteration_state['no_consensus_count'] = 1
        
        # Create mock iteration context
        context = Mock(spec=IterationContext)
        
        # Should not raise errors
        strategy.update_state(context)
        
        # State should be preserved
        assert strategy.iteration_state['consensus_count'] == 2
        assert strategy.iteration_state['no_consensus_count'] == 1
