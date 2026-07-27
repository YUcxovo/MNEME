#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
TEMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT

cd "$REPO_ROOT/backend"
uv run python -m mneme.cli.benchmark_behavior \
    --output "$TEMP_DIR/performance.json" \
    --require-clean
uv run python -m mneme.cli.evaluate_behavior --recorded

install -m 0644 "$TEMP_DIR/performance.json" \
    "$REPO_ROOT/docs/evaluation/behavior/performance.json"

cd "$REPO_ROOT"
uv run --script tools/evaluation/plot_behavior_evaluation.py

printf 'Recorded behavior artifacts and figures written under %s\n' \
    "$REPO_ROOT/docs/evaluation/behavior"
