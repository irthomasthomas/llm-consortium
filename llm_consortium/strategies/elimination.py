"""Elimination Strategy for llm-consortium.

This strategy progressively eliminates underperforming models based on
their confidence scores across iterations.
"""

from .base import ConsortiumStrategy
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class EliminationStrategy(ConsortiumStrategy):
    """
    Strategy that eliminates worst-performing models each iteration based on Arbiter ranking.
    
    Strategy parameters (passed via params dict):
        - eliminate_count: int (default 1)
          Number of lowest-ranked models to eliminate per round.
        - eliminate_fraction: float (default 0.0)
          Proportion of current active models to eliminate per round. If both 
          count and fraction are used, the maximum of the two is applied.
        - keep_minimum: int (default 2)
          Never eliminate if it would drop the active models below this number.
        - elimination_delay: int (default 1)
          Number of iterations to wait before starting elimination.
    """
    
    def _validate_params(self):
        """Validate strategy-specific parameters"""
        self.eliminate_count = int(
            self.params.get('eliminate_count', 1)
        )
        self.eliminate_fraction = float(
            self.params.get('eliminate_fraction', 0.0)
        )
        self.keep_minimum = int(
            self.params.get('keep_minimum', 2)
        )
        self.elimination_delay = int(
            self.params.get('elimination_delay', 1)
        )
        
        if self.eliminate_count < 0:
            raise ValueError("eliminate_count must be non-negative")
        if self.eliminate_fraction < 0 or self.eliminate_fraction > 1:
            raise ValueError("eliminate_fraction must be between 0 and 1")
        if self.keep_minimum < 1:
            raise ValueError("keep_minimum must be at least 1")
        if self.elimination_delay < 0:
            raise ValueError("elimination_delay must be non-negative")
    
    def initialize_state(self):
        """Initialize elimination tracking"""
        super().initialize_state()
        self.iteration_state['eliminated_models'] = set()
        self.iteration_state['iteration_count'] = 0
    
    def select_models(self, available_models: Dict[str, int], 
                     current_prompt: str, iteration: int) -> Dict[str, int]:
        """Select models, excluding eliminated ones"""
        self.iteration_state['iteration_count'] = iteration
        eliminated = self.iteration_state['eliminated_models']
        
        # Filter out eliminated models
        selected = {
            model: count 
            for model, count in available_models.items() 
            if model not in eliminated
        }
        
        # Ensure we don't go below keep_minimum
        if len(selected) < self.keep_minimum:
            # Restore some eliminated models if needed
            eliminated_list = list(eliminated)
            for model in eliminated_list:
                if model in available_models:
                    selected[model] = available_models[model]
                    eliminated.remove(model)
                    if len(selected) >= self.keep_minimum:
                        break
        
        logger.info(f"[EliminationStrategy Iteration {iteration}] "
                   f"Selected {len(selected)} models "
                   f"({len(self.iteration_state['eliminated_models'])} eliminated)")
        return selected
    
    def process_responses(self, successful_responses: List[Dict[str, Any]], 
                         iteration: int) -> List[Dict[str, Any]]:
        """Pass through all responses (no filtering before synthesis)"""
        return successful_responses
    
    def update_state(self, iteration_context: 'IterationContext'):
        """Eliminate worst-ranked models after each iteration"""
        from llm_consortium import IterationContext
        
        synthesis = iteration_context.synthesis
        model_responses = iteration_context.model_responses
        iteration = self.iteration_state['iteration_count']
        
        # Only eliminate after delay period
        if iteration < self.elimination_delay:
            logger.debug(f"[EliminationStrategy] Skipping elimination "
                        f"(iteration {iteration} < delay {self.elimination_delay})")
            return
            
        ranking = synthesis.get('ranking', [])
        if not ranking:
            logger.warning("[EliminationStrategy] No ranking found in synthesis! This strategy requires a ranking-capable arbiter (judging_method='rank').")
            return
            
        eliminated = self.iteration_state['eliminated_models']
        current_active = {r.get('id'): r.get('model') for r in model_responses if r.get('model') not in eliminated and r.get('id') is not None}
        
        if len(current_active) <= self.keep_minimum:
            return
            
        # Count how many we are supposed to eliminate
        target_eliminate = self.eliminate_count
        if self.eliminate_fraction > 0:
            fraction_count = int(len(current_active) * self.eliminate_fraction)
            target_eliminate = max(target_eliminate, fraction_count)
            
        # Prevent eliminating beyond keep_minimum
        max_can_eliminate = len(current_active) - self.keep_minimum
        target_eliminate = min(target_eliminate, max_can_eliminate)
        
        if target_eliminate <= 0:
            return
            
        # The ranking array is ordered [best_id, second_best_id, ... worst_id]
        # Gather active ranked IDs maintaining their order
        # Fallback handling in case of parser mismatch
        active_ranked_ids = [rid for rid in ranking if rid in current_active]
        if not active_ranked_ids:
            return

        # Take the worst-ranked active models
        to_eliminate_ids = active_ranked_ids[-target_eliminate:]
        
        for rid in to_eliminate_ids:
            model = current_active[rid]
            eliminated.add(model)
            logger.info(f"[EliminationStrategy] Eliminated worst-ranked model: {model} (Response ID: {rid})")
