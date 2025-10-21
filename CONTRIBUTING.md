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

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Project Structure

- `llm_consortium/`: Main package directory
  - `__init__.py`: Core implementation
  - `system_prompt.xml`: Default system prompt
  - `arbiter_prompt.xml`: Prompt for the arbiter model
  - `iteration_prompt.xml`: Prompt for iteration refinement
- `tests/`: Test directory
  - `test_llm_consortium.py`: Unit tests for the main package
  - `test_cli.py`: CLI tests
- `examples/`: Example usage and documentation
- `pyproject.toml`: Project configuration
- `README.md`: Project documentation

## Testing

Run the test suite:

```bash
pytest
```

For coverage report:

```bash
pytest --cov=llm_consortium
```

## Code Style

This project follows PEP 8 style guidelines. Use tools like `black` for formatting and `flake8` for linting:

```bash
black llm_consortium tests
flake8 llm_consortium tests
```

## Making Changes

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and write tests for new functionality.

3. Run the test suite to ensure tests pass:
   ```bash
   pytest
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
