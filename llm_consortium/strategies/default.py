from .base import ConsortiumStrategy
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__) # Use specific logger

class DefaultStrategy(ConsortiumStrategy):
    """
    The default strategy:
    - Selects all available models configured in the orchestrator.
    - Performs no processing or filtering on the responses before synthesis.
    """

    def __init__(self, orchestrator, params=None):
        super().__init__(orchestrator, params)
        logger.debug("DefaultStrategy initialized.")

    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        """Selects all available models defined in the orchestrator's config."""
        logger.debug(f"[DefaultStrategy Iteration {iteration}] Selecting all available models: {available_models}")
        # Return a copy to avoid potential modification issues if the caller modifies it
        return available_models.copy()

    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        """Returns the list of successful responses unmodified."""
        logger.debug(f"[DefaultStrategy Iteration {iteration}] Passing through {len(successful_responses)} successful responses without modification.")
        # Return the original list (or a copy if modification is a concern downstream)
        return successful_responses

    # No need to override update_state or initialize_state as this strategy is stateless.

    def prepare_iteration_prompt(self, model_id: str, instance: int, original_prompt: str, iteration: int) -> str:
        """
        Implements a cache-optimized prompt structure for subsequent iterations.
        Places the long, static original prompt BEFORE the dynamic iteration history.
        """
        if not self.orchestrator.iteration_history:
             return original_prompt
             
        prev_synth = self.orchestrator.iteration_history[-1].get("synthesis", {}).get("synthesis", "")
        
        guidance = f"""Iteration Guidance:
Please improve upon the previous iteration based on this synthesis:
{prev_synth}"""

        if getattr(self.orchestrator, 'manual_context', False):
            # Cache-optimized layout: Static content first, dynamic content last
            return f"Original Context/Prompt: {original_prompt}\n---\n{guidance}"
        else:
            return guidance
