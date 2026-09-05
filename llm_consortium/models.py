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
    skip_intermediate_synthesis: bool = Field(default=False, description="Skip full synthesis during intermediate iterations; arbiter provides evaluation and per-model guidance instead")
    per_model_guidance: bool = Field(default=True, description="Generate per-model guidance for the next iteration when skipping intermediate synthesis")
    category: Optional[str] = None
    expected_agreement: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        self.strategy = _normalize_mode_name(self.strategy, "default")
        # rank-cot keeps its dash; other methods are lowercased
        raw_jm = (self.judging_method or "default").strip().lower().replace(" ", "-")
        self.judging_method = raw_jm or "default"
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

    def _final_user_text(self, result: Dict[str, Any]) -> str:
        """Pick the user-facing text. Parse failure => best member response."""
        synth = result.get("synthesis", {}) or {}
        parse_ok = synth.get("parse_success", True)
        text = (synth.get("synthesis") or "").strip()
        if parse_ok and text and text != "[DEFERRED]":
            return text
        # Fallback: ranking[0] member response, else first valid response.
        iterations = result.get("iterations", []) or []
        ranking = synth.get("ranking") or []
        pool: List[Dict[str, Any]] = []
        for it in iterations:
            for r in it.get("model_responses", []):
                if r.get("error") is None and r.get("response"):
                    pool.append(r)
        if ranking:
            by_id = {r.get("id"): r for r in pool}
            for rid in ranking:
                if rid in by_id:
                    logger.warning(
                        "Arbiter parse failure; returning top-ranked member response (id=%s).",
                        rid,
                    )
                    return by_id[rid]["response"]
        if pool:
            logger.warning("Arbiter parse failure; returning first member response.")
            return pool[0]["response"]
        return "Error: Arbiter and member responses unavailable."

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

            # --- Final answer selection ---
            # The user-facing text is ALWAYS either the arbiter's synthesized
            # answer or, when the arbiter violated the JSON contract, the best
            # MEMBER response (never the arbiter's meta-analysis).
            final_synthesis_data = result.get("synthesis", {})
            final_output_text = self._final_user_text(result)
            response.response_json = result
            return final_output_text

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
