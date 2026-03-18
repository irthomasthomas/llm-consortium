#!/bin/bash
set -e

echo "Setting up llm-consortium development environment..."

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    # Check if .venv exists and is valid
    if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
        echo "Activating existing virtual environment..."
        source .venv/bin/activate
    else
        echo "Creating new virtual environment..."
        python -m venv .venv
        source .venv/bin/activate
        
        # Upgrade pip in the new environment
        pip install --upgrade pip
    fi
else
    echo "Already in virtual environment: $VIRTUAL_ENV"
fi

# Install the package with all dependencies
echo "Installing llm-consortium with all dependencies..."
pip install -e ".[embeddings,visualize,dev]"

# Run initial tests
echo "Running tests..."
python -m pytest tests/ -v --cov=llm_consortium --cov-report=term-missing

echo ""
echo "Setup complete!"
echo ""
echo "To activate the virtual environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run the plugin:"
echo "  llm consortium --help"
echo ""
echo "To save a consortium configuration:"
echo "  llm consortium save my-consortium -m gpt-4 -m claude-3-sonnet --arbiter gpt-4"
