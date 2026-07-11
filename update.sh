#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

cd "$(dirname "$0")"

SPORT="${1:-all}"

if [[ ! -d ".venv" ]]; then
    echo "Creating Python virtual environment..."
    python -m venv .venv
fi

source .venv/Scripts/activate

echo "Installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Updating: $SPORT"
python update_all.py --sport "$SPORT"
