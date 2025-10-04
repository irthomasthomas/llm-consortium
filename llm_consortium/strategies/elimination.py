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
    Strategy that eliminates worst-performing models each iteration.
    
    Strategy parameters (passed via params dict):
        - elimination_threshold: float (default 0.6)
          Models with average confidence < this are eliminated
        - keep_minimum: int (default 2)
          Never eliminate below this many models
        - elimination_delay: int (default 1)
          Number of iterations to wait before starting elimination
    """
    
    def _validate_params(self):
        """Validate strategy-specific parameters"""
        self.elimination_threshold = float(
            self.params.get('elimination_threshold', 0.6)
        )
        self.keep_minimum = int(
            self.params.get('keep_minimum', 2)
        )
        self.elimination_delay = int(
            self.params.get('elimination_delay', 1)
        )
        
        if self.elimination_threshold < 0 or self.elimination_threshold > 1:
            raise ValueError("elimination_threshold must be between 0 and 1")
        if self.keep_minimum < 1:
            raise ValueError("keep_minimum must be at least 1")
        if self.elimination_delay < 0:
            raise ValueError("elimination_delay must be non-negative")
    
    def initialize_state(self):
        """Initialize elimination tracking"""
        super().initialize_state()
        self.iteration_state['eliminated_models'] = set()
        self.iteration_state['model_scores'] = {}  # model -> list of confidences
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
        """Eliminate low-confidence models after each iteration"""
        from llm_consortium.orchestrator import IterationContext
        
        synthesis = iteration_context.synthesis
        model_responses = iteration_context.model_responses
        iteration = self.iteration_state['iteration_count']
        
        # Track confidence per model
        for response in model_responses:
            if 'error' not in response:
                model = response['model']
                # Extract confidence from response if available
                confidence = response.get('confidence', 0.5)
                
                # Update running average
                if model not in self.iteration_state['model_scores']:
                    self.iteration_state['model_scores'][model] = []
                self.iteration_state['model_scores'][model].append(confidence)
        
        # Only eliminate after delay period
        if iteration < self.elimination_delay:
            logger.debug(f"[EliminationStrategy] Skipping elimination "
                        f"(iteration {iteration} < delay {self.elimination_delay})")
            return
        
        # Eliminate underperforming models
        eliminated = self.iteration_state['eliminated_models']
        remaining_models = set(iteration_context.selected_models.keys()) - eliminated
        
        if len(remaining_models) > self.keep_minimum:
            models_to_eliminate = []
            
            for model in remaining_models:
                if model in self.iteration_state['model_scores']:
                    confidences = self.iteration_state['model_scores'][model]
                    avg_confidence = sum(confidences) / len(confidences)
                    
                    if avg_confidence < self.elimination_threshold:
                        # Check if eliminating this would keep us above minimum
                        if len(remaining_models) - len(models_to_eliminate) > self.keep_minimum:
                            models_to_eliminate.append(model)
                            logger.info(f"[EliminationStrategy] Marking {model} "
                                       f"for elimination (avg confidence: {avg_confidence:.2f})")
            
            # Actually eliminate the models
            for model in models_to_eliminate:
                eliminated.add(model)
                logger.info(f"[EliminationStrategy] Eliminated {model}")
