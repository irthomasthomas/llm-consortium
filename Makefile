.PHONY: help install install-dev install-embeddings install-visualize test clean

help:
	@echo "llm-consortium development setup"
	@echo ""
	@echo "Available targets:"
	@echo "  install          Install package with basic dependencies"
	@echo "  install-dev      Install with all dependencies including dev tools"
	@echo "  install-embeddings Install with embeddings support"
	@echo "  install-visualize  Install with visualization support"
	@echo "  install-all      Install with all extras (embeddings, visualize, dev)"
	@echo "  test             Run tests"
	@echo "  lint             Run linting"
	@echo "  format           Format code"
	@echo "  clean            Clean build artifacts"
	@echo ""
	@echo "Examples:"
	@echo "  make install-all   # Full development setup"
	@echo "  make install-dev   # Development without embeddings/visualize"

install:
	@echo "Installing llm-consortium with basic dependencies..."
	pip install -e .

install-dev:
	@echo "Installing llm-consortium with development dependencies..."
	pip install -e ".[dev]"

install-embeddings:
	@echo "Installing llm-consortium with embeddings support..."
	pip install -e ".[embeddings]"

install-visualize:
	@echo "Installing llm-consortium with visualization support..."
	pip install -e ".[visualize]"

install-all:
	@echo "Installing llm-consortium with all dependencies..."
	pip install -e ".[embeddings,visualize,dev]"

test:
	@echo "Running tests..."
	pytest tests/ -v --cov=llm_consortium --cov-report=term-missing

lint:
	@echo "Running flake8..."
	flake8 llm_consortium/ tests/ --max-line-length=120 --exclude=__pycache__

format:
	@echo "Formatting code with black..."
	black llm_consortium/ tests/ --line-length=120

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
