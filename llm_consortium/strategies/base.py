from abc import ABC, abstractmethod
from typing import List, Dict, Any, TYPE_CHECKING, Optional

# Avoid circular import for type hinting using TYPE_CHECKING
if TYPE_CHECKING:
    from llm_consortium import ConsortiumOrchestrator, IterationContext # Use relative import if appropriate in final structure '. .'

class ConsortiumStrategy(ABC):
    """
    Abstract Base Class for defining consortium strategies.

    Each strategy determines how models are selected for each iteration
    and how their responses are processed before synthesis. Strategies can
    also maintain state across iterations.
    """

    def __init__(self, orchestrator: 'ConsortiumOrchestrator', params: Optional[Dict[str, Any]] = None):
        """
        Initialize the strategy.

        Args:
            orchestrator: A reference to the main orchestrator instance, providing
                          access to configuration (e.g., models, arbiter) and
                          iteration history if needed.
            params: A dictionary of strategy-specific parameters passed from the
                    configuration (e.g., {'top_k': 3}). Defaults to empty dict.
        """
        self.orchestrator = orchestrator
        self.params = params or {}
        # Dictionary to hold any state the strategy needs to maintain across iterations
        # within a single orchestrate() run. Reset by initialize_state().
        self.iteration_state: Dict[str, Any] = {}
        self._validate_params() # Allow subclasses to validate params on init

    def _validate_params(self):
        """
        Optional method for subclasses to validate parameters passed during initialization.
        Can raise ValueError or TypeError for invalid parameters.
        """
        pass # Default implementation does nothing

    def initialize_state(self):
        """
        Called at the beginning of each `orchestrate()` run to reset or
        initialize any state required by the strategy for that run.
        """
        self.iteration_state = {} # Reset state for a new orchestration run
        # Subclasses can override to perform more specific initialization

    @abstractmethod
    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        """
        **REQUIRED:** Selects which models (and how many instances) to use for the current iteration.

        Args:
            available_models: All models configured for the consortium (name -> count).
                              The strategy should generally select from these.
            current_prompt: The prompt text being sent to the models in this iteration.
                            Useful for strategies that adapt based on the prompt.
            iteration: The current iteration number (1-based).

        Returns:
            A dictionary mapping selected model names to the number of instances
            to use in this iteration (e.g., {"gpt-4o-mini": 1, "claude-3-haiku": 1}).
            Must be a subset of available_models respecting instance counts.
            Return an empty dict {} to indicate no models should run this iteration.
        """
        pass

    @abstractmethod
    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        """
        **REQUIRED:** Processes, filters, or ranks successful model responses before synthesis.

        Args:
            successful_responses: A list of response dictionaries ONLY from models that
                                  completed successfully in the current iteration. Each dict
                                  typically includes keys like "model", "instance", "response" (text),
                                  "confidence", "conversation_id".
            iteration: The current iteration number (1-based).

        Returns:
            A potentially modified list of response dictionaries that should be
            passed to the arbiter for synthesis. This could involve:
            - Filtering out low-quality responses.
            - Ranking responses and selecting a subset (e.g., top N).
            - Modifying response content or metadata (use with caution).
            Return an empty list [] if no responses should be synthesized.
        """
        pass

    def update_state(self, iteration_context: 'IterationContext'):
        """
        **OPTIONAL:** Called at the end of each iteration, allowing the strategy to update
        its internal state based on the full results of the iteration.

        Args:
            iteration_context: An object containing the results of the completed iteration,
                               including the arbiter's `synthesis` dict and the full list
                               of `model_responses` (including errors).
                               Provides context like `iteration_context.iteration`,
                               `iteration_context.synthesis['confidence']`, etc.
        """
        # Default implementation does nothing.
        # Subclasses can override this to track model performance, update scores,
        # manage elimination lists, etc., using `self.iteration_state`.
        pass

    def get_instance_system_prompt(self, model: str, instance: int, default_prompt: Optional[str]) -> Optional[str]:
        """
        **OPTIONAL:** Allows a strategy to modify the system prompt per-instance.

        Args:
            model: The name of the model being invoked (e.g., 'gpt-4').
            instance: The instance number (1-based index).
            default_prompt: The base system prompt configured for the consortium.

        Returns:
            The modified system prompt, or None if no system prompt should be used.
            Default implementation returns the `default_prompt` unmodified.
        """
        return default_prompt

    def prepare_iteration_prompt(self, model_id: str, instance: int, original_prompt: str, iteration: int) -> str:
        """
        **OPTIONAL:** Prepares the prompt for a subsequent iteration (iteration > 1).
        By default, this provides a naive implementation. Strategies should override this
        to create cache-optimized prompts.

        Args:
            model_id: The ID of the model being prompted.
            instance: The model instance number.
            original_prompt: The initial user prompt.
            iteration: The current iteration number.

        Returns:
            The formatted prompt string for this iteration.
        """
        if not self.orchestrator.iteration_history:
             return original_prompt
             
        prev_synth = self.orchestrator.iteration_history[-1].get("synthesis", {}).get("synthesis", "")
        
        guidance = f"""Iteration Guidance:\nPlease improve upon the previous iteration based on this synthesis:\n{prev_synth}"""
        
        if getattr(self.orchestrator, 'manual_context', False):
             return f"Original Context/Prompt: {original_prompt}\n---\n{guidance}"
        else:
             return guidance
