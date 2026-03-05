import llm
import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .db import DatabaseConnection

logger = logging.getLogger(__name__)

def resolve_alias_options(model_id: str) -> Optional[Dict[str, Any]]:
    """Fallback for llm.resolve_alias_options which was removed in newer llm versions.
    Currently returns None to gracefully ignore alias options if unavailable.
    """
    return None

class ConsortiumConfig(BaseModel):
    models: Dict[str, int]  # Maps model names to instance counts
    system_prompt: Optional[str] = None
    confidence_threshold: float = 0.8
    max_iterations: int = 3
    minimum_iterations: int = 1
    arbiter: Optional[str] = None
    judging_method: str = "default"
    strategy: Optional[str] = None
    strategy_params: Optional[Dict[str, Any]] = None
    manual_context: bool = Field(default=False, description="Use manual context management instead of automatic conversation objects")

    def to_dict(self):
        return self.model_dump()

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

def parse_models(models: List[str], count: int) -> Dict[str, int]:
    """Parse list of model descriptors into a configuration dictionary."""
    model_dict = {}
    for entry in models:
        if ":" in entry:
            parts = entry.rsplit(":", 1)
            model_id = parts[0]
            try:
                model_count = int(parts[1])
            except ValueError:
                model_count = count  # fallback to default count
        else:
            model_id = entry
            model_count = count
        
        model_dict[model_id] = model_dict.get(model_id, 0) + model_count
    return model_dict

def _get_consortium_configs() -> Dict[str, ConsortiumConfig]:
    """Retrieve all saved consortium configurations from database."""
    db = DatabaseConnection.get_connection()
    if "consortium_configs" not in db.table_names():
        return {}
    
    configs = {}
    for row in db["consortium_configs"].rows:
        try:
             config_data = json.loads(row.get("config") or row.get("config_json"))
             configs[row["name"]] = ConsortiumConfig.from_dict(config_data)
        except Exception as e:
             logger.error(f"Failed to load consortium config '{row['name']}': {e}")
    return configs

def _save_consortium_config(name: str, config: ConsortiumConfig) -> None:
    """Save a consortium configuration to the database."""
    db = DatabaseConnection.get_connection()
    db["consortium_configs"].insert({
        "name": name,
        "config": json.dumps(config.to_dict()),
        "created_at": datetime.now().isoformat()
    }, pk="name", replace=True)

class DummyModel(llm.Model):
    model_id = "dummy"
    can_stream = True
    
    def execute(self, prompt, stream, response, conversation):
        message = f"DUMMY ECHO: {prompt.prompt}"
        if stream:
            yield message
        else:
            return message

class ConsortiumModel(llm.Model):
    class Options(llm.Options):
        max_iterations: Optional[int] = None
        system_prompt: Optional[str] = None

    def __init__(self, model_id: str, config: ConsortiumConfig):
        super().__init__()
        self.model_id = str(model_id)
        self.config = config
        self._orchestrator = None

    def __str__(self):
        return f"Consortium Model: {self.model_id}"

    def get_orchestrator(self):
        if self._orchestrator is None:
            # Lazy import to avoid circular dependency
            from .orchestrator import ConsortiumOrchestrator
            try:
                self._orchestrator = ConsortiumOrchestrator(self.config)
            except Exception as e:
                raise llm.ModelError(f"Failed to initialize consortium: {e}")
        return self._orchestrator

    def execute(self, prompt, stream, response, conversation):
        orchestator = self.get_orchestrator()
        
        consortium_id = str(uuid.uuid4())
        
        history = None
        if conversation:
            try:
                history_text = []
                for entry in conversation.responses:
                    history_text.append(f"Human: {entry.prompt.prompt}")
                    history_text.append(f"Assistant: {entry.text()}")
                if history_text:
                    history = "\n".join(history_text)
            except:
                pass

        result = orchestator.orchestrate(prompt.prompt, conversation_history=history, consortium_id=consortium_id)
        
        synthesis_text = result.get("synthesis", {}).get("synthesis", "")
        if synthesis_text:
            yield synthesis_text
        else:
            yield str(result)
