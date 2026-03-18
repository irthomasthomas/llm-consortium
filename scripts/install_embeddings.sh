#!/bin/bash
# Helper script to install embeddings dependencies for llm-consortium

echo "Installing embeddings dependencies for llm-consortium..."

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Not in a virtual environment. Installing to system Python."
    echo "Note: You may need to use --break-system-packages on Arch Linux."
    
    # Try with uv first (recommended for Arch)
    if command -v uv &> /dev/null; then
        echo "Using uv to install..."
        uv pip install --system "llm-consortium[embeddings]"
    else
        echo "Using pip..."
        pip install "llm-consortium[embeddings]"
    fi
else
    echo "Installing in virtual environment: $VIRTUAL_ENV"
    pip install "llm-consortium[embeddings]"
fi

echo ""
echo "Installation complete!"
echo ""
echo "To verify, run:"
echo "  llm consortium strategies"
echo ""
echo "You should now see 'semantic' in the list of available strategies."
