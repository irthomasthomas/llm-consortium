# llm-consortium API Documentation

## Core Classes

### ConsortiumConfig
Configuration object for consortium settings.

#### Attributes
- models: Dict of model names and their weights
- arbiter: Model name to use as arbiter
- strategy: Strategy name for model selection
- strategy_params: Parameters for the strategy

### ConsortiumOrchestrator
Main orchestrator class for managing model interactions.

#### Methods
- __init__(config): Initialize with a ConsortiumConfig
- orchestrate(prompt): Run the orchestration process
- config (property): Access the configuration object

## Helper Functions

### create_consortium
Convenience function to create a configured orchestrator.

python
def create_consortium(models, arbiter, strategy="elimination", strategy_params=None, **kwargs):
    """Create a consortium with the specified configuration."""


## Strategies

### EliminationStrategy
Eliminates models with confidence below threshold.

#### Parameters
- elimination_threshold: Minimum confidence (default: 0.8)
- keep_minimum: Minimum models to keep (default: 2)

### VotingStrategy
Selects response based on consensus.

#### Parameters
- similarity_threshold: Minimum similarity threshold (default: 0.75)
- require_majority: Whether to require majority vote (default: True)
