#!/bin/bash
# Quick setup script for llm-consortium
# This handles the externally-managed-environment issue

set -e

echo "=== llm-consortium Quick Setup ==="

# Check if uv is available (preferred on Arch)
if command -v uv &> /dev/null; then
    echo "Using uv for installation..."
    
    # Create a virtual environment with uv
    if [ ! -d ".venv" ]; then
        uv venv
    fi
    
    # Activate the environment
    source .venv/bin/activate
    
    # Install with uv
    uv pip install -e ".[embeddings,visualize,dev]"
    
    echo "Installation complete with uv."
else
    echo "uv not found, using regular venv..."
    
    # Create virtual environment
    python -m venv .venv
    source .venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install
    pip install -e ".[embeddings,visualize,dev]"
fi

# Register the plugin with llm
echo "Registering plugin with llm..."
llm install -e .

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment: source .venv/bin/activate"
echo "  2. Test the installation: llm consortium --help"
echo "  3. Save a consortium configuration:"
echo "     llm consortium save my-consortium \\"
echo "       -m gpt-4 -m claude-3-sonnet \\"
echo "       --arbiter gpt-4 \\"
echo "       --confidence-threshold 0.8"
echo ""
echo "Note: The virtual environment is already activated in this shell."
