#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/../../scripts/batch_scale.py" \
    "$SCRIPT_DIR/margarita.json" \
    --servings 12 \
    --method shaken \
    --units oz
