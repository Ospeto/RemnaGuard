#!/bin/bash
# RemnaGuard DNS Configuration Wrapper

# Resolve script directory to allow running from anywhere
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "Checking for Python3..."
if ! command -v python3 &> /dev/null
then
    echo "Error: python3 is not installed."
    exit 1
fi

python3 scripts/dns_wizard.py
