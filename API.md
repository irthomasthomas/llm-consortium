# llm-consortium API Documentation

## Core Classes

### ConsortiumConfig
Configuration object for consortium settings. Built upon `pydantic.BaseModel`.

#### Attributes
- `models: Dict[str, int]`: Maps model names to their instance counts.
- `system_prompt: Optional[str]`: Override for the default system prompt.
- `confidence_threshold: float`: Minimum confidence score to achieve (0.0-1.0, default 0.8).
- `max_iterations: int`: Maximum rounds of iterations (default 3).
- `minimum_iterations: int`: Minimum rounds of iterations (default 1).
- `arbiter: Optional[str]`: Model name to use as the arbiter.
- `judging_method: str`: Method the arbiter uses (e.g., 'default' or 'rank').
- `manual_context: bool`: Use manual context management instead of automatic conversation objects.

### ConsortiumOrchestrator
Main orchestrator class for managing model interactions.

#### Methods
- `__init__(config: ConsortiumConfig)`: Initialize with a `ConsortiumConfig`.
- `orchestrate(prompt: str, conversation_history: str = "", consortium_id: Optional[str] = None) -> Dict[str, Any]`: Run the orchestration process to synthesize answers.
- `enable_tracing(trace_id: Optional[str] = None) -> str`: Enable prompt tracing internally.
- `disable_tracing() -> None`: Disables prompt tracing and saves traces.
- `reset_model_conversations() -> None`: Resets internal conversation state for models.
- `reset_arbiter_conversation() -> None`: Resets internal conversation state for the arbiter.

## Helper Functions

### create_consortium
Convenience function to create a configured orchestrator.

```python
def create_consortium(
    models: list[str],
    confidence_threshold: float = 0.8,
    max_iterations: int = 3,
    min_iterations: int = 1,
    arbiter: Optional[str] = None,
    judging_method: str = "default",
    system_prompt: Optional[str] = None,
    default_count: int = 1,
    raw: bool = False,
) -> ConsortiumOrchestrator:
    """
    Create and return a ConsortiumOrchestrator.
    - models: list of model names. To specify instance counts, use the format "model:count".
    - system_prompt: if not provided, the default system prompt is used.
    """
```
