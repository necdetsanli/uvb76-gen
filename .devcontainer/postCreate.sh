#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Create/sync .venv deterministically (includes dev dependencies)
uv sync --extra dev

# Install git hooks if this is a git repo
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  uv run pre-commit install
fi

echo "Dev environment is ready."
