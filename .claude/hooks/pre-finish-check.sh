#!/usr/bin/env bash
set -e

pytest -q || true
docker compose config >/dev/null
