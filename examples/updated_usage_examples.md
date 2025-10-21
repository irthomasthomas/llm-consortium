# Updated Usage Examples

## Basic Usage

python
from llm_consortium import create_consortium

# Simple consortium with default elimination strategy
consortium = create_consortium(
    models=['gpt-4o-mini', 'claude-3-haiku'],
    arbiter='gpt-4o'
)

result = consortium.orchestrate("What is 2+2?")
print(result['synthesis']['synthesis'])


## Advanced Configuration

python
from llm_consortium import create_consortium

# Consortium with custom strategy parameters
consortium = create_consortium(
    models=['gpt-4o-mini', 'claude-3-haiku', 'gemini-pro'],
    arbiter='gpt-4o',
    strategy='elimination',
    strategy_params={
        'elimination_threshold': 0.9,  # Higher threshold
        'keep_minimum': 1              # Keep only the best
    }
)

# Access configuration details
print(f"Models: {consortium.config.models}")
print(f"Strategy: {consortium.config.strategy}")
print(f"Params: {consortium.config.strategy_params}")


## CLI Usage

bash
# Save a configuration
llm consortium save research-team \
  -m gpt-4o-mini \
  -m claude-3-haiku \
  --arbiter gpt-4o \
  --strategy elimination \
  --strategy-params '{"elimination_threshold": 0.85}'

# Use the saved configuration
llm -m research-team 'Summarize the latest research on quantum computing'

# List saved configurations
llm consortium list

# Show a specific configuration
llm consortium show research-team


## Creating Custom Strategies

python
from llm_consortium.strategies.base import StrategyBase

class CustomStrategy(StrategyBase):
    def select_response(self, responses):
        # Implement custom logic
        pass

