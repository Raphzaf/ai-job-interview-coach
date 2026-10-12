#!/usr/bin/env bash
# Assemble the files a Hugging Face Docker Space needs to run the coach.
#   bash deploy/huggingface/prepare_space.sh <output-dir>
# The output contains only the coach: Dockerfile, requirements, app/, sample
# documents and the Space card (README.md with the Space configuration).
set -euo pipefail

OUT="${1:?usage: prepare_space.sh <output-dir>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "Output directory $OUT is not empty; choose a new one." >&2
  exit 1
fi
mkdir -p "$OUT/data"

cp "$ROOT/Dockerfile" "$ROOT/requirements.txt" "$ROOT/.dockerignore" "$OUT/"
cp -r "$ROOT/app" "$OUT/app"
cp -r "$ROOT/data/examples" "$OUT/data/examples"
cp "$ROOT/deploy/huggingface/space_card.md" "$OUT/README.md"
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "Space content ready in $OUT:"
(cd "$OUT" && find . -maxdepth 2 -not -path "./app/*" | sort)
