#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

command -v python3 >/dev/null || { echo 'Install Python 3 with pip before running setup.' >&2; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 24 LTS (includes npm) before running setup.' >&2; exit 1; }

if command -v uv >/dev/null 2>&1; then
  uv_binary="$(command -v uv)"
else
  uv_binary="$project_root/.tools/uv/bin/uv"
  if [ ! -x "$uv_binary" ]; then
    python3 -m pip install --target "$project_root/.tools/uv" --no-cache-dir --disable-pip-version-check 'uv==0.12.12'
  fi
fi

# Keep downloaded Python runtimes and package caches inside this project.
export UV_CACHE_DIR="$project_root/.tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$project_root/.tools/python"
export UV_PYTHON_BIN_DIR="$project_root/.tools/bin"
export npm_config_cache="$project_root/.tools/npm-cache"

"$uv_binary" sync --directory "$project_root/backend" --locked --python 3.13

python3 - <<'PY'
from pathlib import Path
import secrets

destination = Path('backend/.env')
if not destination.exists():
    lines = Path('backend/.env.example').read_text().splitlines()
    lines = [
        'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50)
        if line.startswith('DJANGO_SECRET_KEY=') else line
        for line in lines
    ]
    destination.write_text('\n'.join(lines) + '\n')
    destination.chmod(0o600)
    print('Created backend/.env with a unique local secret.')
PY

backend/.venv/bin/python backend/manage.py migrate
npm --prefix frontend ci

echo 'Setup complete. Run make backend and make frontend in separate terminals.'
