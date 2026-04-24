import llm
import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .db import DatabaseConnection

logger = logging.getLogger(__name__)


def _normalize_mode_name(value: Optional[str], default: str) -> str:
    normalized = (value or default).strip().lower()
    return normalized or default

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
    embedding_backend: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_cache_enabled: bool = True
    manual_context: bool = Field(default=False, description="Use manual context management instead of automatic conversation objects")
    category: Optional[str] = None
    expected_agreement: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        self.strategy = _normalize_mode_name(self.strategy, "default")
        self.judging_method = _normalize_mode_name(self.judging_method, "default")
        if self.embedding_backend is not None:
            self.embedding_backend = self.embedding_backend.strip().lower() or None
        if self.embedding_model is not None:
            self.embedding_model = self.embedding_model.strip() or None

        # Elimination strategy requires ranking output, so force rank judging
        if self.strategy == "elimination" and self.judging_method != "rank":
            self.judging_method = "rank"

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
             config = ConsortiumConfig.from_dict(config_data)
             # Add database metadata to the config object
             config.created_at = row.get("created_at")
             configs[row["name"]] = config
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
        return f"Consortium: {self.model_id}"

    @property
    def description(self):
        models_summary = ", ".join(f"{v}x {k}" for k, v in self.config.models.items())
        return f"Consortium strategy '{self.config.strategy or 'default'}' using models: {models_summary}"

    def get_orchestrator(self):
        if self._orchestrator is None:
            # Lazy import to avoid circular dependency
            from .orchestrator import ConsortiumOrchestrator
            try:
                self._orchestrator = ConsortiumOrchestrator(self.config, config_name=self.model_id)
            except Exception as e:
                raise llm.ModelError(f"Failed to initialize consortium: {e}")
        return self._orchestrator

    def execute(self, prompt, stream, response, conversation):
        consortium_id = str(uuid.uuid4())
        """Execute the consortium synchronously"""
        try:
            # Extract conversation history from the conversation object directly
            conversation_history = ""
            if conversation and hasattr(conversation, 'responses') and conversation.responses:
                logger.info(f"Processing conversation with {len(conversation.responses)} previous exchanges")
                history_parts = []
                for resp in conversation.responses:
                    # Handle prompt format
                    human_prompt = "[prompt unavailable]"
                    if hasattr(resp, 'prompt') and resp.prompt:
                        if hasattr(resp.prompt, 'prompt'):
                            human_prompt = resp.prompt.prompt
                        else:
                            human_prompt = str(resp.prompt)

                    # Handle response text format
                    assistant_response = "[response unavailable]"
                    if hasattr(resp, 'text') and callable(resp.text):
                        assistant_response = resp.text()
                    elif hasattr(resp, 'response') and resp.response:
                        assistant_response = resp.response

                    # Format the history exchange
                    history_parts.append(f"Human: {human_prompt}")
                    history_parts.append(f"Assistant: {assistant_response}")

                if history_parts:
                    conversation_history = "\n\n".join(history_parts)
                    logger.info(f"Successfully formatted {len(history_parts)//2} exchanges from conversation history")

            # Check if a system prompt was provided via --system option
            if hasattr(prompt, 'system') and prompt.system:
                # Create a copy of the config with the updated system prompt
                updated_config = ConsortiumConfig(**self.config.to_dict())
                updated_config.system_prompt = prompt.system
                # Create a new orchestrator with the updated config
                from .orchestrator import ConsortiumOrchestrator
                orchestrator = ConsortiumOrchestrator(updated_config)
                result = orchestrator.orchestrate(prompt.prompt, conversation_history=conversation_history, consortium_id=consortium_id)
            else:
                # Use the default orchestrator with the original config
                orchestrator = self.get_orchestrator()
                result = orchestrator.orchestrate(prompt.prompt, conversation_history=conversation_history, consortium_id=consortium_id)

            # --- BEGIN REVISED FALLBACK LOGIC ---
            # Check result details from orchestrate
            final_synthesis_data = result.get("synthesis", {}) # This dict contains parsed fields and raw_arbiter_response
            raw_arbiter_response = final_synthesis_data.get("raw_arbiter_response", "")
            parsed_synthesis = final_synthesis_data.get("synthesis", "") # This is the parsed <synthesis> content
            analysis_text = final_synthesis_data.get("analysis", "")

            # Determine if parsing failed or synthesis is insufficient
            # Check 1: Explicit parsing failure message
            # Check 2: Parsed synthesis is empty, but raw response is not (likely missing <synthesis> tag)
            # Check 3: Parsed synthesis is exactly the raw response (parser fallback returned raw) AND no explicit success analysis
            is_fallback = ("Parsing failed" in analysis_text) or \
                          (not parsed_synthesis and raw_arbiter_response) or \
                          (parsed_synthesis == raw_arbiter_response and raw_arbiter_response) # Simpler check: If parsed == raw and raw is not empty, it's likely the fallback.

            if is_fallback:
                 final_output_text = raw_arbiter_response if raw_arbiter_response else "Error: Arbiter response unavailable or empty."
                 logger.warning("Arbiter response parsing failed or synthesis missing/empty. Returning raw arbiter response for logging.")
            else:
                 # Parsing seemed successful, return the clean synthesis
                 final_output_text = parsed_synthesis

            # Store the full result JSON in the response object for logging (existing code)
            response.response_json = result # Ensure this is still done before returning
            # Return the determined final text (clean synthesis or raw fallback)
            return final_output_text
            # --- END REVISED FALLBACK LOGIC ---

        except Exception as e:
            logger.exception(f"Consortium execution failed: {e}")
            raise llm.ModelError(f"Consortium execution failed: {e}")

# Register models function for the plugin system
def register_models(register):
    """Register all saved consortiums as models."""
    from .db import DatabaseConnection
    import json
    
    try:
        db = DatabaseConnection.get_connection()
        if "consortium_configs" not in db.table_names():
            return
        
        for row in db["consortium_configs"].rows:
            name = row.get("name")
            if name:
                try:
                    config_data = json.loads(row.get("config", "{}"))
                    # Use the existing ConsortiumModel class
                    model = ConsortiumModel(name, ConsortiumConfig.from_dict(config_data))
                    register(model)
                    logger.debug(f"Registered consortium model: {name}")
                except Exception as e:
                    logger.error(f"Failed to register consortium model '{name}': {e}")
    except Exception as e:
        logger.error(f"Failed to register consortium models: {e}")
