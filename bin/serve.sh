#!/usr/bin/env bash
# Phase 4: build the static site from texts/ and serve it locally.
#   bin/serve.sh [port]     (default 8080)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
port="${1:-8080}"

python3 "$ROOT/site/build.py"
echo "serving: http://localhost:$port/"
exec python3 -m http.server "$port" --directory "$ROOT/site/out"
