#!/usr/bin/env bash
set -e

if command -v ruff >/dev/null 2>&1; then
  ruff check app tests || true
fi

if command -v black >/dev/null 2>&1; then
  black --check app tests || true
fi
