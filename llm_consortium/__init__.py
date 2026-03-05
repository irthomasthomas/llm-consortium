import logging
import sys
import llm

from .db import (
    DatabaseConnection,
    log_response,
    logs_db_path,
    user_dir
)

from .models import (
    ConsortiumConfig,
    ConsortiumModel,
    DummyModel,
    _get_consortium_configs
)

from .orchestrator import (
    ConsortiumOrchestrator,
    create_consortium,
    IterationContext
)

from .cli import register_commands

def setup_logging() -> None:
    """Configure logging to write to both file and console."""
    log_path = user_dir() / "consortium.log"

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(str(log_path))
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

setup_logging()
logger = logging.getLogger(__name__)
logger.debug("llm_karpathy_consortium module is being imported")

@llm.hookimpl
def register_models(register):
    logger.debug("Registering saved consortium models")
    
    try:
        dummy_model = DummyModel()
        register(dummy_model, aliases=("dummy",))
        logger.debug("Registered dummy model for testing")
    except Exception as e:
        logger.error(f"Failed to register dummy model: {e}")
    
    try:
        configs = _get_consortium_configs()
        for name, config in configs.items():
            try:
                if not config.models or not config.arbiter:
                     logger.warning(f"Skipping registration of invalid consortium '{name}': Missing models or arbiter.")
                     continue
                model_instance = ConsortiumModel(name, config)
                register(model_instance, aliases=(name,))
                logger.debug(f"Registered consortium model: {name}")
            except Exception as e:
                logger.error(f"Failed to register consortium model '{name}': {e}")
    except Exception as e:
        logger.error(f"Failed to load or register consortium configurations: {e}")

class KarpathyConsortiumPlugin:
    @staticmethod
    @llm.hookimpl
    def register_commands(cli):
        # Defers to the actual implementation in cli.py which is exported through our __init__.py
        pass 

__all__ = [
    'KarpathyConsortiumPlugin', 'ConsortiumModel', 'ConsortiumConfig',
    'ConsortiumOrchestrator', 'create_consortium', 'register_commands',
    'register_models', 'log_response', 'DatabaseConnection', 'logs_db_path',
    'user_dir', 'IterationContext'
]

__version__ = "0.7.1"