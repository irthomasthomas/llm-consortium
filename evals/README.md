# Model Consortium Evaluation Suite

This directory contains a suite of tools for evaluating and benchmarking the effectiveness of different consortium strategies, specifically focusing on the **Semantic Filtering** vs. the **Default** synthesis methods.

## Overview

The evaluation pipeline consists of three main phases:

1. **Benchmarking**: Running parallel prompts against multiple strategies.
2. **Blind Judging**: Using an impartial LLM to evaluate the quality of the outputs without knowing which strategy produced them.
3. **Analysis**: Aggregating the results to determine win rates, disagreement frequencies, and geometric metrics.

## Tools

### 1. `benchmark_runner.py`
Executes a suite of prompts defined in `prompts.json` across different consortium configurations.

**Usage:**
```bash
python evals/benchmark_runner.py \
    --prompts evals/prompts.json \
    --models "gpt-4o:3,claude-3-5-sonnet:3" \
    --arbiter gpt-4o \
    --output evals/results.json
```

### 2. `blind_judge.py`
Performs a blind A/B test of the results. It presents the outputs to a "Judge" model in a randomized order.

**Usage:**
```bash
python evals/blind_judge.py \
    --input evals/results.json \
    --judge-model gpt-4o \
    --output evals/judgments.json
```

### 3. `analyze_results.py`
Generates a comprehensive report on the evaluation run.

**Usage:**
```bash
python evals/analyze_results.py \
    --results evals/results.json \
    --judgments evals/judgments.json \
    --output evals/report.json
```

## Data Files

- `prompts.json`: A curated list of prompts categorized by difficulty and expected agreement. Use this as a template for your own evaluations.

## Metrics Explained

- **Geometric Confidence Delta**: Measures how much semantic filtering "tightened" the consensus space compared to the raw outputs.
- **Disagreement Frequency**: The percentage of runs where the models produced multiple semantic clusters (indicating a non-trivial consensus was required).
- **Win Rate**: The percentage of times the semantic strategy was judged superior to the default strategy.

## replay_arbiter.py

Replays **recorded production arbiter prompts** (mined from the llm logs DB at
`~/.config/io.datasette.llm/logs.db`) through both delivery modes against
live models:

```
python evals/replay_arbiter.py "glm-5.2-nim,ling-3.0-flash" <n_failing> <n_passing> <max_prompt_chars>
```

- `inline` mode sends the recorded legacy prompt verbatim (data + trailing instructions).
- `system` mode splits at the `</arbiter_prompt>` seam: data in the user turn, instructions in `system=`.
- Cases are selected from historically failing (`<confidence>` missing) and passing arbiter calls; score uses the parser's exact `<confidence>` regex.

Motivation: synthetic local rigs have no failure headroom; replaying real
recorded failures directly validates whether the system-channel split repairs
observed production failures.
