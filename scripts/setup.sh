#!/usr/bin/env bash
# One-time setup for LEO AI development.
set -e
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp -n .env.example .env || true
echo "Setup complete. Edit .env with your API keys, then run: python main.py"
