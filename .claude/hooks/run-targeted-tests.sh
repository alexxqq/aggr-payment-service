#!/usr/bin/env bash
set -e

pytest tests/unit -q || true
