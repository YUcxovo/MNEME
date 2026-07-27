#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT/backend"
uv run python -m mneme.cli.evaluate_behavior --recorded

cd "$REPO_ROOT"
uv run --script tools/evaluation/plot_behavior_evaluation.py

printf 'Recorded behavior artifacts and figures written under %s\n' \
    "$REPO_ROOT/docs/evaluation/behavior"
