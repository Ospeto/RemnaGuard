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

# Ensure Virtual Environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv || {
        echo "❌ Error: Failed to create virtual environment."
        echo "   If you are on Ubuntu/Debian, please run:"
        echo "   sudo apt-get update && sudo apt-get install python3-venv"
        exit 1
    }
fi

# Activate venv
source .venv/bin/activate

# Install PyYAML if missing
if ! pip show PyYAML &> /dev/null; then
    echo "⬇️  Installing dependencies (PyYAML)..."
    pip install PyYAML > /dev/null
fi

# Check for credentials in .env
if [ -f ".env" ]; then
    if ! grep -q "CLOUDFLARE_API_TOKEN" .env; then
        echo "⚠️  Warning: CLOUDFLARE_API_TOKEN not found in .env"
        echo "   The Cloudflare sync will be disabled until you add it."
    fi
else
    echo "⚠️  Warning: .env file missing. Run install.sh first or create it."
fi

echo "✅ Environment OK."
echo "Starting Wizard..."
sleep 1

# Launch the interactive Python wizard
python3 scripts/dns_wizard.py
