#!/usr/bin/env bash
# Phase 3c: theme -> gated text, one author per run.
#
#   bin/generate.sh <author> [theme]
#
# author = a key of authors.yaml (poe, emerson). With no theme, the first
# authors.yaml theme that has no text in texts/<author>/ yet is used — so
# running this twice yields two different texts. All real work is in
# pipeline/stitch.py; this wrapper exists for command-line ergonomics.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
author="${1:?usage: bin/generate.sh <author> [theme]}"

if [ $# -ge 2 ]; then
  exec python3 "$ROOT/pipeline/stitch.py" --author "$author" --theme "$2"
else
  exec python3 "$ROOT/pipeline/stitch.py" --author "$author"
fi
