"""Tests for the EliminationStrategy."""

import pytest
from unittest.mock import Mock, MagicMock
from llm_consortium.strategies.elimination import EliminationStrategy
from llm_consortium import IterationContext
from llm_consortium.models import ConsortiumConfig


class TestEliminationStrategy:
    """Test cases for EliminationStrategy."""
    
    def test_init_with_default_params(self):
        """Test initialization with default parameters."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator)
        
        assert strategy.eliminate_count == 1
        assert strategy.eliminate_fraction == 0.0
        assert strategy.keep_minimum == 2
        assert strategy.elimination_delay == 1

    def test_config_forces_rank_judging_for_elimination(self):
        config = ConsortiumConfig(
            models={"gpt-4": 1, "claude": 1},
            arbiter="arbiter",
            strategy="elimination",
            judging_method="default",
        )

        assert config.judging_method == "rank"
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        mock_orchestrator = Mock()
        params = {
            'eliminate_count': 2,
            'eliminate_fraction': 0.5,
            'keep_minimum': 3,
            'elimination_delay': 2
        }
        strategy = EliminationStrategy(mock_orchestrator, params)
        
        assert strategy.eliminate_count == 2
        assert strategy.eliminate_fraction == 0.5
        assert strategy.keep_minimum == 3
        assert strategy.elimination_delay == 2
    
    def test_validate_params_invalid_fraction(self):
        """Test validation fails with invalid fraction."""
        mock_orchestrator = Mock()
        with pytest.raises(ValueError, match="eliminate_fraction must be between 0 and 1"):
            EliminationStrategy(mock_orchestrator, {'eliminate_fraction': 1.5})
    
    def test_validate_params_invalid_keep_minimum(self):
        """Test validation fails with invalid keep_minimum."""
        mock_orchestrator = Mock()
        with pytest.raises(ValueError, match="keep_minimum must be at least 1"):
            EliminationStrategy(mock_orchestrator, {'keep_minimum': 0})
    
    def test_initialize_state(self):
        """Test state initialization."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator)
        strategy.initialize_state()
        
        assert strategy.iteration_state['eliminated_models'] == set()
        assert strategy.iteration_state['iteration_count'] == 0
    
    def test_select_models_no_elimination_first_iteration(self):
        """Test model selection on first iteration (no elimination yet)."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator, {'elimination_delay': 2})
        strategy.initialize_state()
        
        available = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        selected = strategy.select_models(available, "test prompt", 1)
        
        assert selected == available
    
    def test_select_models_with_elimination(self):
        """Test model selection with eliminated models."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator)
        strategy.initialize_state()
        
        # Simulate some eliminated models
        strategy.iteration_state['eliminated_models'] = {'gemini'}
        
        available = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        selected = strategy.select_models(available, "test prompt", 2)
        
        assert selected == {'gpt-4': 1, 'claude': 1}
        assert 'gemini' not in selected
    
    def test_select_models_respects_keep_minimum(self):
        """Test that selection respects keep_minimum parameter."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator, {'keep_minimum': 2})
        strategy.initialize_state()
        
        # Eliminate all but one model
        strategy.iteration_state['eliminated_models'] = {'gpt-4', 'claude'}
        
        available = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        selected = strategy.select_models(available, "test prompt", 2)
        
        # Should restore at least keep_minimum models
        assert len(selected) >= 2
    
    def test_process_responses_passthrough(self):
        """Test that process_responses passes through all responses."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(mock_orchestrator)
        
        responses = [
            {'model': 'gpt-4', 'response': 'A'},
            {'model': 'claude', 'response': 'B'}
        ]
        
        processed = strategy.process_responses(responses, 1)
        assert processed == responses
    
    def test_update_state_eliminates_bottom_ranked(self):
        """Test that bottom ranked models get eliminated."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(
            mock_orchestrator, 
            {'eliminate_count': 1, 'keep_minimum': 2, 'elimination_delay': 0}
        )
        strategy.initialize_state()
        
        # Create mock iteration context
        responses = [
            {'model': 'gpt-4', 'id': 'resp_1', 'response': 'A'},
            {'model': 'claude', 'id': 'resp_2', 'response': 'B'},
            {'model': 'gemini', 'id': 'resp_3', 'response': 'C'}
        ]
        
        # Ranking: 1st gpt-4, 2nd gemini, 3rd claude (worst)
        mock_synthesis = {'ranking': ['resp_1', 'resp_3', 'resp_2']}
        context = Mock(spec=IterationContext)
        context.model_responses = responses
        context.synthesis = mock_synthesis
        context.selected_models = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        
        strategy.update_state(context)
        
        # claude ranks last, so it should be eliminated
        assert 'claude' in strategy.iteration_state['eliminated_models']
        assert 'gpt-4' not in strategy.iteration_state['eliminated_models']
        assert 'gemini' not in strategy.iteration_state['eliminated_models']
    
    def test_update_state_respects_keep_minimum(self):
        """Test that elimination respects keep_minimum."""
        mock_orchestrator = Mock()
        strategy = EliminationStrategy(
            mock_orchestrator, 
            {'eliminate_count': 2, 'keep_minimum': 2, 'elimination_delay': 0}
        )
        strategy.initialize_state()
        
        # We have 3 models, want to eliminate 2, keep_minimum=2
        # Should only eliminate 1
        responses = [
            {'model': 'gpt-4', 'id': 'resp_1', 'response': 'A'},
            {'model': 'claude', 'id': 'resp_2', 'response': 'B'},
            {'model': 'gemini', 'id': 'resp_3', 'response': 'C'}
        ]
        
        mock_synthesis = {'ranking': ['resp_1', 'resp_2', 'resp_3']}
        context = Mock(spec=IterationContext)
        context.model_responses = responses
        context.synthesis = mock_synthesis
        context.selected_models = {'gpt-4': 1, 'claude': 1, 'gemini': 1}
        
        strategy.update_state(context)
        
        # Should only eliminate 1 model to keep minimum of 2
        assert len(strategy.iteration_state['eliminated_models']) == 1
        assert 'gemini' in strategy.iteration_state['eliminated_models']
