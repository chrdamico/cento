#!/usr/bin/env bash
# Phase 1a: download the Project Gutenberg plain-text files listed in
# authors.yaml into corpus/raw/<author>/pg<id>.txt. Cached: a book is fetched
# once, ever. Polite: sequential, and only the cache URL (no mirror scraping).
#
# The book ids in authors.yaml are never trusted blindly: after download the
# header's Author: line must contain the configured author name, or we delete
# the file and abort loudly.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/corpus/raw"
mkdir -p "$RAW"

authors=$(python3 "$ROOT/pipeline/authors.py" | python3 -c '
import json, sys
for a, cfg in json.load(sys.stdin).items():
    for gid in cfg["gutenberg"]:
        print(a, gid, cfg["name"])
')

while read -r author gid name; do
  dir="$RAW/$author"
  file="$dir/pg$gid.txt"
  mkdir -p "$dir"

  if [ -s "$file" ]; then
    echo "cached: $file"
  else
    url="https://www.gutenberg.org/cache/epub/$gid/pg$gid.txt"
    echo "fetching: $url"
    curl -fsSL --retry 3 -o "$file.part" "$url"
    mv "$file.part" "$file"
    sleep 2   # politeness between fetches
  fi

  # Verify the id points at the right author. The PG header carries
  # "Author: ..." within the first ~40 lines.
  if ! head -n 40 "$file" | grep -qi "Author: .*${name##* }"; then
    echo "ERROR: pg$gid does not look like a work by '$name':" >&2
    head -n 40 "$file" | grep -i '^\(Title\|Author\):' >&2 || true
    rm -f "$file"
    exit 1
  fi
  title=$(head -n 40 "$file" | grep -i '^Title:' | head -1 || true)
  echo "  ok: $author pg$gid — ${title:-<no Title header>}"
done <<< "$authors"

echo
echo "all books fetched and verified; now: python3 pipeline/segment.py"
