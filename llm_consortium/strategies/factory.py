from .base import ConsortiumStrategy
from .default import DefaultStrategy
from .elimination import EliminationStrategy
from .role import RoleStrategy
from .voting import VotingStrategy

# Try to import SemanticClusteringStrategy - requires embeddings extras
try:
    from .semantic import SemanticClusteringStrategy
    SEMANTIC_AVAILABLE = True
except ImportError as e:
    SEMANTIC_AVAILABLE = False
    SemanticClusteringStrategy = None
    _semantic_import_error = str(e)

from typing import Dict, Any, Optional, Type, TYPE_CHECKING
import logging
import importlib

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from llm_consortium import ConsortiumOrchestrator

# --- Strategy Registry ---
_strategy_registry: Dict[str, Type[ConsortiumStrategy]] = {
    "default": DefaultStrategy,
    "elimination": EliminationStrategy,
    "role": RoleStrategy,
    "voting": VotingStrategy,
}

_strategy_descriptions: Dict[str, str] = {
    "default": "Run all configured members and synthesize their responses.",
    "elimination": "Use arbiter ranking to remove weaker models across iterations.",
    "role": "Assign distinct cognitive roles or personalities to member instances.",
    "voting": "Group similar answers and prefer the consensus cluster.",
}

# Conditionally add semantic strategy if available
if SEMANTIC_AVAILABLE:
    _strategy_registry["semantic"] = SemanticClusteringStrategy
    _strategy_descriptions["semantic"] = "Cluster response embeddings and keep the densest semantic consensus region."
else:
    logger.debug(f"SemanticClusteringStrategy not available: {_semantic_import_error}")


def list_available_strategies() -> Dict[str, Dict[str, str]]:
    """Return discoverable built-in strategies with human-readable descriptions."""
    return {
        name: {
            "class_name": strategy_class.__name__,
            "description": _strategy_descriptions.get(name, "No description available."),
        }
        for name, strategy_class in sorted(_strategy_registry.items())
    }


def create_strategy(strategy_name: Optional[str], orchestrator: 'ConsortiumOrchestrator', params: Optional[Dict[str, Any]] = None) -> ConsortiumStrategy:
    """
    Factory function to create and initialize strategy instances based on name.
    """
    params = params or {}
    normalized_name = (strategy_name or 'default').lower().strip()
    if not normalized_name:
        normalized_name = 'default'

    logger.debug(f"Attempting to create strategy '{normalized_name}' with params: {params}")

    # 1. Check the explicit registry first
    StrategyClass = _strategy_registry.get(normalized_name)

    # 2. If not in registry, attempt dynamic import
    if StrategyClass is None:
        logger.debug(f"Strategy '{normalized_name}' not in registry. Attempting dynamic import...")
        try:
            module_name = f".{normalized_name}"
            class_name = "".join(part.capitalize() for part in normalized_name.split('_')) + "Strategy"

            strategy_module = importlib.import_module(module_name, package=__package__)
            StrategyClass = getattr(strategy_module, class_name, None)

            if StrategyClass and issubclass(StrategyClass, ConsortiumStrategy):
                logger.info(f"Dynamically loaded strategy '{normalized_name}' -> {StrategyClass.__name__}")
            else:
                logger.warning(f"Dynamic import failed: Could not find valid class '{class_name}' in module '{module_name}'.")
                StrategyClass = None

        except ImportError:
            logger.warning(f"Dynamic import failed: Could not import module '{module_name}' for strategy '{normalized_name}'.")
            StrategyClass = None
        except AttributeError:
             logger.warning(f"Dynamic import failed: Class '{class_name}' not found in module '{module_name}'.")
             StrategyClass = None
        except Exception as e:
             logger.exception(f"Unexpected error during dynamic import of strategy '{normalized_name}': {e}")
             StrategyClass = None

    # 3. Instantiate the class if found, otherwise raise error
    if StrategyClass:
        try:
            instance = StrategyClass(orchestrator, params)
            logger.debug(f"Successfully instantiated strategy '{normalized_name}'")
            return instance
        except Exception as e:
            logger.exception(f"Error initializing strategy class '{StrategyClass.__name__}' for strategy '{normalized_name}': {e}")
            raise ValueError(f"Initialization failed for strategy '{normalized_name}': {e}") from e
    else:
        available = list(_strategy_registry.keys())
        
        # Provide helpful error message for semantic strategy
        if normalized_name == "semantic" and not SEMANTIC_AVAILABLE:
            raise ValueError(
                f"The 'semantic' strategy requires optional dependencies. "
                f"Install with: pip install llm-consortium[embeddings]"
            )
        
        logger.error(f"Unknown strategy requested: '{normalized_name}'. Available: {available}")
        raise ValueError(f"Unknown strategy: '{normalized_name}'. Available: {', '.join(available)}")
