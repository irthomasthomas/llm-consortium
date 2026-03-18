"""LLM Consortium - Implementing Karpathy's model consortium approach."""
import os
import sys
import llm

# First-run dependency check (runs silently once per import)
_dep_check_done = False

def _check_and_install_deps():
    """Check and auto-install missing dependencies on first import."""
    global _dep_check_done
    if _dep_check_done or os.environ.get('LLM_CONSORTIUM_SKIP_DEP_CHECK') == '1':
        return
    
    _dep_check_done = True
    import subprocess
    import importlib
    
    core_deps = {
        'httpx': 'httpx',
        'sqlite_utils': 'sqlite-utils',
        'numpy': 'numpy',
        'colorama': 'colorama',
        'pydantic': 'pydantic',
    }
    
    missing = []
    for module, package in core_deps.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"[llm-consortium] Installing: {', '.join(missing)}", file=sys.stderr)
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '--quiet'
        ] + missing, stderr=subprocess.DEVNULL)

# Run check on import
try:
    _check_and_install_deps()
except Exception:
    pass  # Silently fail if auto-install doesn't work

# Version
__version__ = "0.8.0"

# Import core classes for public API and to satisfy tests
from .db import DatabaseConnection
from .models import ConsortiumConfig, ConsortiumModel
from .orchestrator import ConsortiumOrchestrator, IterationContext

# Import CLI and model registration hooks for llm
from .cli import register_commands
import llm
import json
import logging

logger = logging.getLogger(__name__)

@llm.hookimpl
def register_models(register):
    """Register all saved consortiums as models."""
    try:
        db = DatabaseConnection.get_connection()
        if "consortium_configs" not in db.table_names():
            return
        
        for row in db["consortium_configs"].rows:
            name = row.get("name")
            if name:
                try:
                    config_data = json.loads(row.get("config", "{}"))
                    config = ConsortiumConfig.from_dict(config_data)
                    model = ConsortiumModel(name, config)
                    register(model)
                    logger.debug(f"Registered consortium model: {name}")
                except Exception as e:
                    logger.error(f"Failed to register consortium model '{name}': {e}")
    except Exception as e:
        logger.error(f"Failed to register consortium models: {e}")

__all__ = [
    "ConsortiumOrchestrator",
    "IterationContext",
    "ConsortiumConfig",
    "ConsortiumModel",
    "DatabaseConnection",
    "register_commands",
    "register_models",
]
