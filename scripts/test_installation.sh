#!/bin/bash
# Test if llm-consortium is properly installed

set -e

echo "=== Testing llm-consortium Installation ==="

# Check if we're in a virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Virtual environment: $VIRTUAL_ENV"
else
    echo "WARNING: Not in a virtual environment"
    echo "Attempting to activate .venv..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "Activated virtual environment"
    fi
fi

# Check Python
echo ""
echo "Python version:"
python --version

# Check if llm-consortium is installed
echo ""
echo "Checking llm-consortium package:"
pip show llm-consortium || echo "Package not installed via pip"

# Check if plugin is registered
echo ""
echo "Checking llm plugins:"
llm plugins 2>/dev/null | grep -i consortium || echo "Plugin not registered"

# Check dependencies
echo ""
echo "Checking dependencies:"
python -c "import llm_consortium; print('llm_consortium imported successfully')" 2>/dev/null || echo "Failed to import llm_consortium"

# Test basic functionality
echo ""
echo "Testing basic functionality:"
llm consortium --help 2>/dev/null | head -5 || echo "llm consortium command not available"

echo ""
echo "=== Test Complete ==="
