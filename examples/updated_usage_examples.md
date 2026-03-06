# Updated Usage Examples

## Basic Usage

```python
from llm_consortium import create_consortium

# Simple consortium with default elimination strategy
consortium = create_consortium(
    models=['gpt-4o-mini', 'claude-3-haiku'],
    arbiter='gpt-4o'
)

result = consortium.orchestrate("What is 2+2?")
print(result['synthesis']['synthesis'])
```

## Advanced Configuration

```python
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
```

## CLI Usage

```bash
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
```

## Creating Custom Strategies

```python
from llm_consortium.strategies.base import ConsortiumStrategy

class CustomStrategy(ConsortiumStrategy):
    def select_models(self, available_models, current_prompt, iteration):
        # Select models for this iteration
        return available_models
        
    def process_responses(self, successful_responses, iteration):
        # Process and filter responses
        return successful_responses
```

## Semantic Strategy and Visualization

```python
from llm_consortium import create_consortium
from llm_consortium.visualization import generate_run_visualization

# The semantic strategy clusters model embeddings to find the most dense response region 
# before synthesis.
consortium = create_consortium(
    models=['gpt-4o:3', 'claude-3-haiku:3'],
    arbiter='gpt-4o',
    strategy='semantic',
    strategy_params={
        'clustering_algorithm': 'dbscan',
        'eps': 0.35,
        'min_samples': 2
    }
)

result = consortium.orchestrate("Explain the implications of quantum entanglement on cryptography.")

# After the run completes, you can visualize the semantic clusters for the run ID
run_id = result['metadata']['consortium_id']
print(f"Synthesized Response: {result['synthesis']['synthesis']}")

# This generates a t-SNE projection HTML figure and persists its coordinates in the sqlite DB.
figure = generate_run_visualization(run_id)
# You can display the figure if running inside a Jupyter Notebook or explicitly export it:
# figure.write_html("run_visualization.html")
```
