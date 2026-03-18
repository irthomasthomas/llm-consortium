# Contributing to LLM Consortium

Thank you for your interest in contributing to the LLM Consortium project! This guide will help you get started with development and understand how to contribute effectively.

## Project Overview

LLM Consortium is a plugin for the `llm` package that implements a model consortium system with iterative refinement and response synthesis. It orchestrates multiple language models to collaboratively solve complex problems through structured dialogue, evaluation, and arbitration.

## Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd llm-consortium
   ```

2. Initialize development environment with `uv`:
   ```bash
   uv sync --all-extras
   ```

## Project Structure

- `llm_consortium/`: Main package directory
  - `__init__.py`: Core implementation
  - `system_prompt.xml`, `arbiter_prompt.xml`, `iteration_prompt.xml`: Prompt templates
- `tests/`: Unit and integration tests
- `evals/`: Evaluation and benchmarking tools
- `scripts/`: Shared setup and utility scripts
- `docs/`: In-depth documentation and research notes
- `examples/`: Example usage and demonstration configs
- `pyproject.toml`: Project configuration
- `README.md`: Main project entry point

## Testing

Run the test suite:

```bash
uv run pytest
```

For coverage report:

```bash
uv run pytest --cov=llm_consortium
```

## Code Style

This project follows PEP 8 style guidelines. Use tools like `black` for formatting and `flake8` for linting:

```bash
uv run black llm_consortium tests
uv run flake8 llm_consortium tests
```

## Making Changes

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and write tests for new functionality.

3. Run the test suite to ensure tests pass:
   ```bash
   uv run pytest
   ```

4. Commit your changes with descriptive commit messages.

5. Push your branch and create a pull request.

## Pull Request Process

1. Update the README.md or documentation with details of changes if appropriate.
2. Update the CHANGELOG.md with details of your changes.
3. The PR will be merged once it has been reviewed and approved.

## Feature Requests and Bug Reports

Please use the issue tracker to submit feature requests and bug reports.

When reporting a bug, please include:
- A clear description of the issue
- Steps to reproduce
- Expected vs. actual behavior
- Environment details (OS, Python version, etc.)

## Discussion and Questions

For questions or discussions about development, please use the Discussions tab in the repository.

Thank you for contributing to LLM Consortium!

## Development Setup

### Prerequisites
- Python 3.8+
- `llm` CLI tool installed
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/irthomasthomas/llm-consortium.git
cd llm-consortium

# Use the quick setup script (handles venv creation)
./scripts/quick_setup.sh

# Or manually:
python -m venv .venv
source .venv/bin/activate
pip install -e ".[embeddings,visualize,dev]"
llm install -e .
```

### Dependency Management

The package has three dependency groups:

1. **Core** (always installed): Required for basic functionality
2. **Embeddings**: For semantic clustering features
3. **Visualize**: For plotly-based visualizations
4. **Dev**: Development tools (pytest, black, flake8)

Install specific groups:
```bash
pip install -e ".[embeddings]"     # Just embeddings
pip install -e ".[visualize]"      # Just visualization
pip install -e ".[dev]"            # Just dev tools
pip install -e ".[embeddings,visualize,dev]"  # Everything
```

### Running Tests

```bash
make test
# Or:
pytest tests/ -v --cov=llm_consortium
```

### Auto-Dependency Installation

The package includes a first-run dependency check that will automatically install missing core dependencies. To disable this behavior (e.g., in CI), set:
```bash
export LLM_CONSORTIUM_SKIP_DEP_CHECK=1
```
