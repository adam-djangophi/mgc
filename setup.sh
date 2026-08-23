#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/init_db.py

printf '\nSetup complete.\n'
printf 'Run the API with: ./run_api.sh\n'
printf 'Run the worker with: .venv/bin/python -m mgc.main\n'
