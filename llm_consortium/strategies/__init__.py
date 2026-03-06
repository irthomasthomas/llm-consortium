# Makes 'strategies' a Python package
from .base import ConsortiumStrategy
from .default import DefaultStrategy
from .factory import create_strategy
from .semantic import SemanticClusteringStrategy

# Import specific strategy classes here when implemented
# from .round_robin import RoundRobinStrategy
# from .counterfactual_regret import CounterfactualRegretStrategy
# from .deep_bloom import DeepBloomStrategy

__all__ = [
    "ConsortiumStrategy",
    "DefaultStrategy",
    "SemanticClusteringStrategy",
    "create_strategy",
    # Add other strategy class names to __all__ when implemented
    # "RoundRobinStrategy",
    # "CounterfactualRegretStrategy",
    # "DeepBloomStrategy",
]

# Optional: Log when the package is initialized (for debugging imports)
import logging
logger = logging.getLogger(__name__)
logger.debug("strategies package initialized")
