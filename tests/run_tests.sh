#!/bin/bash

# Script to run tests with coverage reporting

# Make sure we're in the right directory
cd "$(dirname "$0")"

# Check if pytest and pytest-cov are installed
python -m pip install -q pytest pytest-cov

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running tests with coverage reporting...${NC}"

# Run the tests with coverage
python -m pytest -xvs --cov=llm_consortium --cov-report=term-missing --cov-report=html:coverage_html tests/

# Get the exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]
then
    echo -e "${GREEN}All tests passed!${NC}"
    echo ""
    echo -e "${YELLOW}Coverage report generated in 'coverage_html' directory${NC}"
    echo -e "${YELLOW}Open 'coverage_html/index.html' to view the detailed report${NC}"
else
    echo -e "${RED}Some tests failed. Please check the output above.${NC}"
fi

exit $EXIT_CODE
