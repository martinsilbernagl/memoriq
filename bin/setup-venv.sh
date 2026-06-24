#!/bin/bash
# Memoriq Virtual Environment Setup

set -e

MEMORIQ_HOME="$HOME/.memoriq"
VENV_PATH="$MEMORIQ_HOME/venv"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"
if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "[Memoriq] ERROR: Python $required_version+ required, found $python_version"
    exit 1
fi

echo "[Memoriq] Setting up virtual environment..."

# Create venv if not exists
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
    echo "[Memoriq] Virtual environment created at $VENV_PATH"
fi

# Activate and install dependencies
source "$VENV_PATH/bin/activate"

pip install --upgrade pip
pip install -r "$MEMORIQ_HOME/requirements.txt"

# Verify mcp is installed
if ! python -c "import mcp" 2>/dev/null; then
    echo "[Memoriq] ERROR: Failed to install mcp module"
    exit 1
fi

echo "[Memoriq] Dependencies installed successfully"
echo "[Memoriq] Virtual environment ready at $VENV_PATH"

