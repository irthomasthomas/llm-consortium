from .base import ConsortiumStrategy
from .default import DefaultStrategy
# Import other specific strategy classes here when they are implemented
# e.g., from .round_robin import RoundRobinStrategy
# e.g., from .counterfactual_regret import CounterfactualRegretStrategy
# e.g., from .deep_bloom import DeepBloomStrategy
from typing import Dict, Any, Optional, Type, TYPE_CHECKING
import logging
import importlib

logger = logging.getLogger(__name__) # Use specific logger

if TYPE_CHECKING:
    from llm_consortium import ConsortiumOrchestrator # Use relative import if needed '. .'

# --- Strategy Registry ---
# Stores mappings from strategy names (lowercase) to their implementation classes.
# Allows dynamic registration or discovery if needed later.
_strategy_registry: Dict[str, Type[ConsortiumStrategy]] = {
    "default": DefaultStrategy,
    # Add other built-in strategies here:
    # "round_robin": RoundRobinStrategy,
    # "counterfactual_regret": CounterfactualRegretStrategy,
    # "deep_bloom": DeepBloomStrategy,
}

# --- Future: Mechanism to Register Custom Strategies ---
# def register_strategy(name: str, strategy_class: Type[ConsortiumStrategy]):
#     """Allows external plugins or user code to register custom strategies."""
#     if not issubclass(strategy_class, ConsortiumStrategy):
#         raise TypeError("Registered class must be a subclass of ConsortiumStrategy")
#     normalized_name = name.lower().strip()
#     if normalized_name in _strategy_registry:
#         logger.warning(f"Overwriting previously registered strategy: '{normalized_name}'")
#     _strategy_registry[normalized_name] = strategy_class
#     logger.info(f"Registered custom strategy: '{normalized_name}' -> {strategy_class.__name__}")


def create_strategy(strategy_name: Optional[str], orchestrator: 'ConsortiumOrchestrator', params: Optional[Dict[str, Any]] = None) -> ConsortiumStrategy:
    """
    Factory function to create and initialize strategy instances based on name.

    Args:
        strategy_name: The name of the strategy to create (case-insensitive).
                       Defaults to 'default' if None or empty.
        orchestrator: The orchestrator instance, passed to the strategy constructor.
        params: Strategy-specific parameters, passed to the strategy constructor.

    Returns:
        An initialized instance of the requested ConsortiumStrategy subclass.

    Raises:
        ValueError: If the requested strategy_name is not found in the registry
                    and dynamic loading fails or results in an invalid class.
    """
    params = params or {}
    # Normalize the strategy name (lowercase, default to 'default')
    normalized_name = (strategy_name or 'default').lower().strip()
    if not normalized_name: # Handle empty string case
        normalized_name = 'default'

    logger.debug(f"Attempting to create strategy '{normalized_name}' with params: {params}")

    # 1. Check the explicit registry first
    StrategyClass = _strategy_registry.get(normalized_name)

    # 2. If not in registry, attempt dynamic import (optional, based on naming convention)
    if StrategyClass is None:
        logger.debug(f"Strategy '{normalized_name}' not in registry. Attempting dynamic import...")
        try:
            # Assume module name matches strategy name (e.g., 'round_robin' -> round_robin.py)
            module_name = f".{normalized_name}" # Relative import from current package
            # Assume class name follows CamelCase convention (e.g., 'round_robin' -> RoundRobinStrategy)
            class_name = "".join(part.capitalize() for part in normalized_name.split('_')) + "Strategy"

            # Dynamically import the module relative to the current package ('strategies')
            strategy_module = importlib.import_module(module_name, package=__package__)

            # Get the class from the imported module
            StrategyClass = getattr(strategy_module, class_name, None)

            if StrategyClass and issubclass(StrategyClass, ConsortiumStrategy):
                logger.info(f"Dynamically loaded strategy '{normalized_name}' -> {StrategyClass.__name__}")
                # Optional: Add to registry? Could be useful for listing available strategies later.
                # _strategy_registry[normalized_name] = StrategyClass
            else:
                logger.warning(f"Dynamic import failed: Could not find valid class '{class_name}' in module '{module_name}'.")
                StrategyClass = None # Reset to None if dynamic loading failed

        except ImportError:
            logger.warning(f"Dynamic import failed: Could not import module '{module_name}' for strategy '{normalized_name}'.")
            StrategyClass = None # Import failed
        except AttributeError:
             logger.warning(f"Dynamic import failed: Class '{class_name}' not found in module '{module_name}'.")
             StrategyClass = None # Class not found
        except Exception as e:
             logger.exception(f"Unexpected error during dynamic import of strategy '{normalized_name}': {e}")
             StrategyClass = None # Other error


    # 3. Instantiate the class if found, otherwise raise error
    if StrategyClass:
        try:
            # Instantiate the strategy, passing orchestrator and params
            instance = StrategyClass(orchestrator, params)
            logger.debug(f"Successfully instantiated strategy '{normalized_name}'")
            return instance
        except Exception as e:
            # Catch errors during the strategy's __init__ or _validate_params
            logger.exception(f"Error initializing strategy class '{StrategyClass.__name__}' for strategy '{normalized_name}': {e}")
            raise ValueError(f"Initialization failed for strategy '{normalized_name}': {e}") from e
    else:
        # If not found in registry and dynamic loading failed or wasn't attempted
        logger.error(f"Unknown strategy requested: '{normalized_name}'. Available: {list(_strategy_registry.keys())}")
        raise ValueError(f"Unknown strategy: '{normalized_name}'")

# Register elimination strategy
from .elimination import EliminationStrategy
_strategy_registry["elimination"] = EliminationStrategy

# Register voting strategy
from .voting import VotingStrategy
_strategy_registry["voting"] = VotingStrategy
