#!/bin/bash
# RemnaGuard DNS Configuration Wrapper

# Resolve script directory to allow running from anywhere
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "======================================="
echo "   🛡️  RemnaGuard Setup Assistant"
echo "======================================="

echo "Checking environment..."

# Check for Python 3
if ! command -v python3 &> /dev/null
then
    echo "❌ Error: python3 is not installed."
    echo "   Please install Python 3 to run the configuration wizard."
    exit 1
fi

# Ensure Virtual Environment exists (to avoid breaking system packages)
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install PyYAML if missing
if ! pip show PyYAML &> /dev/null; then
    echo "⬇️  Installing dependencies (PyYAML)..."
    pip install PyYAML > /dev/null
fi

echo "✅ Environment OK."
echo "Starting Wizard..."
sleep 1

# Launch the interactive Python wizard
python3 scripts/dns_wizard.py
