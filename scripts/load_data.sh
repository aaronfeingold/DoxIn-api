#!/bin/bash

# Data Import Script for Invoice Processing System
# Loads Case Study Data.xlsx into PostgreSQL database

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
EXCEL_FILE="${PROJECT_ROOT}/assets/Case Study Data.xlsx"
PYTHON_SCRIPT="${SCRIPT_DIR}/load_excel_data.py"

echo "Invoice Processing System - Data Import"
echo "======================================"

# Check if Excel file exists
if [ ! -f "$EXCEL_FILE" ]; then
    echo "Error: Excel file not found at $EXCEL_FILE"
    exit 1
fi

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Check for required environment variables
if [ -z "$DATABASE_URL" ]; then
    echo "Warning: DATABASE_URL environment variable not set."
    echo "Using default: postgresql://user:pass@localhost/invoices"
    echo ""
fi

# Check if Poetry is installed and dependencies are set up
echo "Checking Python dependencies..."
cd "${SCRIPT_DIR}/.."
if command -v poetry &> /dev/null; then
    poetry install --no-root --quiet 2>/dev/null || echo "Poetry dependencies already installed"
else
    echo "Warning: Poetry not found. Make sure dependencies are installed manually."
fi

echo ""
echo "Starting data import..."
echo "Excel file: $EXCEL_FILE"
echo "Database: ${DATABASE_URL:-postgresql://user:pass@localhost/invoices}"
echo ""

# Run the import with Poetry if available, otherwise use system python
cd "${SCRIPT_DIR}/.."
if command -v poetry &> /dev/null; then
    poetry run python -m scripts.load_excel_data "$EXCEL_FILE"
else
    python -m scripts.load_excel_data "$EXCEL_FILE"
fi

echo ""
echo "Data import completed successfully!"
echo ""
echo "You can now:"
echo "1. Start the Flask backend server"
echo "2. Use the API to query imported data"
echo "3. Test LLM invoice extraction against real data"
