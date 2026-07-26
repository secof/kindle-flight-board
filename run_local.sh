#!/usr/bin/env bash
set -e

# Change directory to the repository root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

# Check Python 3 availability
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in PATH."
    exit 1
fi

# Create virtual environment if it does not exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
echo "⚙️  Activating virtual environment ..."
source "$VENV_DIR/bin/activate"

# Install/update dependencies
echo "📥 Installing / verifying backend dependencies ..."
pip install -q --upgrade pip
pip install -r backend/requirements.txt

# Run backend development server
echo "🚀 Starting backend development server at http://localhost:8000 ..."
echo "   Endpoints available:"
echo "   - Health Check: http://localhost:8000/health"
echo "   - Kindle Board Image: http://localhost:8000/board.png"
echo "   - Flight JSON API: http://localhost:8000/api/flights"
echo ""

PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
