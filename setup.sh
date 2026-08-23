#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/init_db.py

printf '\nSetup complete. Activate the environment with:\n'
printf 'source .venv/bin/activate\n'
