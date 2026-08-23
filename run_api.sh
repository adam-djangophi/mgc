#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$project_root/.venv"

if [[ ! -x "$venv/bin/python" || ! -x "$venv/bin/uvicorn" ]]; then
    printf 'Missing .venv. Run ./setup.sh first.\n' >&2
    exit 1
fi

cd "$project_root"
"$venv/bin/python" -m pip install uvicorn
exec "$venv/bin/uvicorn" mgc.app:app --reload
