# LLM Consortium

## Inspiration

Based on Karpathy's observation:

> "I find that recently I end up using all of the models and all the time. One aspect is the curiosity of who gets what, but the other is that for a lot of problems they have this 'NP Complete' nature to them, where coming up with a solution is significantly harder than verifying a candidate solution. So your best performance will come from just asking all the models, and then getting them to come to a consensus."

This plugin for the `llm` package implements a model consortium system with iterative refinement and response synthesis. It orchestrates multiple language models to collaboratively solve complex problems through structured dialogue, evaluation, and arbitration.

## Core Algorithm Flow

```mermaid
flowchart TD
    A[Start] --> B[Get Model Responses]
    B --> C[Synthesize Responses]
    C --> D{Check Confidence}
    D -- Confidence ≥ Threshold --> E[Return Final Result]
    D -- Confidence < Threshold --> F{Max Iterations Reached?}
    F -- No --> G[Prepare Next Iteration]
    G --> B
    F -- Yes --> E
```

## Features

- **Multi-Model Orchestration**: Coordinate responses from multiple models in parallel.
- **Iterative Refinement**: Automatically refine output until a confidence threshold is achieved.
- **Advanced Arbitration**: Uses a designated arbiter model to synthesize and evaluate responses.
- **Database Logging**: SQLite-backed logging of all interactions.
- **Configurable Parameters**: Adjustable confidence thresholds, iteration limits, and model selection.
- **Flexible Model Instance Counts**: Specify individual instance counts via the syntax `model:count`.  
  *If no count is specified, a default instance count (default: 1) is used.*

## New Model Instance Syntax

You can now define different numbers of instances per model by appending `:count` to the model name. For example:
- `"o3-mini:1"` runs 1 instance of _o3-mini_.
- `"gpt-4o:2"` runs 2 instances of _gpt-4o_.
- `"gemini-2:3"` runs 3 instances of _gemini-2_.

## Installation

First, get [llm](https://github.com/simonw/llm):

Using `uv`:
```bash
uv tool install llm
```
Using `pipx`:
```bash
pipx install llm
```
Then install the consortium plugin:
```bash
llm install llm-consortium
```

## Command Line Usage

The `consortium` command now defaults to the `run` subcommand for concise usage.

Basic usage:
```bash
llm consortium "What are the key considerations for AGI safety?"
```

This command will:
1. Send your prompt to multiple models in parallel (using the specified instance counts, if provided).
2. Gather responses along with analysis and confidence ratings.
3. Use an arbiter model to synthesize these responses.
4. Iterate to refine the answer until a specified confidence threshold or maximum iteration count is reached.

### Options

- `-m, --model`: Model to include in the consortium. To specify instance counts, use the format `model:count` (default models include: `claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `gpt-4`, and `gemini-pro`).
- `--arbiter`: The arbiter model (default: `claude-3-opus-20240229`).
- `--confidence-threshold`: Minimum required confidence (default: `0.8`).
- `--max-iterations`: Maximum rounds of iterations (default: `3`).
- `--min-iterations`: Minimum iterations to perform (default: `1`).
- `--system`: Custom system prompt.
- `--output`: Save detailed results to a JSON file.
- `--stdin/--no-stdin`: Append additional input from stdin (default: enabled).
- `--raw`: Output raw responses from both the arbiter and individual models (default: enabled).

Advanced example:
```bash
llm consortium "Your complex query" \
  -m o3-mini -n 1 \
  -m gpt-4o -n 2 \
  -m gemini-2 -n 3 \
  --arbiter gemini-2 \
  --confidence-threshold 1 \
  --max-iterations 4 \
  --min-iterations 3 \
  --output results.json
```

### Managing Consortium Configurations

You can save a consortium configuration as a model for reuse. This allows you to quickly recall a set of model parameters in subsequent queries.

#### Saving a Consortium as a Model
```bash
llm consortium save my-consortium \
    --model claude-3-opus-20240229 \
    --model gpt-4 \
    --arbiter claude-3-opus-20240229 \
    --confidence-threshold 0.9 \
    --max-iterations 5 \
    --min-iterations 1 \
    --system "Your custom system prompt"
```

Once saved, you can invoke your custom consortium like this:
```bash
llm -m my-consortium "What are the key considerations for AGI safety?"
```

## Programmatic Usage

Use the `create_consortium` helper to configure an orchestrator in your Python code. For example:

```python
from llm_consortium import create_consortium

orchestrator = create_consortium(
    models=["o3-mini:1", "gpt-4o:2", "gemini-2:3"],
    confidence_threshold=1,
    max_iterations=4,
    min_iterations=3,
    arbiter="gemini-2",
    raw=True
)

result = orchestrator.orchestrate("Your prompt here")
print(f"Synthesized Response: {result['synthesis']['synthesis']}")
```

## License

MIT License

## Credits

Developed as part of the LLM ecosystem and inspired by Andrej Karpathy’s insights on collaborative model consensus.

## Changelog

- **v0.3.1**:
  - Introduced the `model -n ` syntax for flexible model instance allocation.
  - Improved confidence calculation and logging.
  - Updated consortium configuration management.
