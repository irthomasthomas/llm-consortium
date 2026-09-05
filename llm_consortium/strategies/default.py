from .base import ConsortiumStrategy, safe_prev_synthesis
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
        Uses per-model guidance when available (from skip_intermediate_synthesis mode).
        """
        if not self.orchestrator.iteration_history:
             return original_prompt
             
        last_iteration = self.orchestrator.iteration_history[-1]
        synthesis_data = last_iteration.get("synthesis", {})
        prev_synth = safe_prev_synthesis(synthesis_data)

        # Check for per-model guidance (from rank-cot or skip_intermediate_synthesis)
        model_guidance = synthesis_data.get("model_guidance", {})
        guidance_key = f"{model_id}_{instance}"
        specific_guidance = model_guidance.get(guidance_key) or model_guidance.get(f"{model_id}_0", "")

        if specific_guidance:
            # Use per-model guidance as the primary feedback
            guidance = f"""Iteration Guidance:
Your specific feedback for improvement:
{specific_guidance}

Previous synthesis (for reference):
{prev_synth if prev_synth and prev_synth != '[DEFERRED]' else '[No synthesis was produced in the previous round - focus on the feedback above.]'}"""
        else:
            # Fallback: use synthesis-based guidance
            refinement_areas = synthesis_data.get("refinement_areas", [])
            refinement_text = ""
            if refinement_areas:
                refinement_text = "\nFocus particularly on these refinement areas:\n"
                for area in refinement_areas:
                    refinement_text += f"- {area}\n"

            guidance = f"""Iteration Guidance:
Please improve upon the previous iteration based on this synthesis:
{prev_synth}{refinement_text}"""

        if getattr(self.orchestrator, 'manual_context', False):
            # Cache-optimized layout: Static content first, dynamic content last
            return f"Original Context/Prompt: {original_prompt}\n---\n{guidance}"
        else:
            return guidance
