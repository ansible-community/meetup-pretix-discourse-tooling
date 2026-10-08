#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "==> isort (fix import ordering)..."
uv run isort --profile black --quiet scripts/*.py main.py

echo "==> ruff format..."
uv run ruff format scripts/*.py main.py

echo "==> ruff check --fix..."
uv run ruff check --fix scripts/*.py main.py

echo "==> Syntax check (py_compile)..."
uv run python3 -c "
import py_compile, glob
files = glob.glob('scripts/*.py') + ['main.py']
for f in files:
    py_compile.compile(f, doraise=True)
" && echo "    All files compile OK."

echo "==> Done."
