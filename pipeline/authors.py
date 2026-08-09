"""Read authors.yaml without PyYAML.

The file is deliberately constrained: two indent levels, scalar values,
lists of scalars. This parser handles exactly that shape and nothing more —
if authors.yaml grows real YAML features, switch to a real parser.

Usable as a module (load()) or CLI: `python3 authors.py [author [key]]`
prints JSON.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHORS_YAML = os.path.join(ROOT, "authors.yaml")


def _scalar(s):
    s = s.strip()
    if s.startswith(("'", '"')) and s.endswith(s[0]) and len(s) >= 2:
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        return s


def load(path=AUTHORS_YAML):
    authors = {}
    author = key = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            body = line.strip()
            if indent == 0 and body.endswith(":"):
                author = body[:-1]
                authors[author] = {}
                key = None
            elif body.startswith("- "):
                authors[author].setdefault(key, []).append(_scalar(body[2:]))
            elif ":" in body:
                k, _, v = body.partition(":")
                key = k.strip()
                if v.strip():
                    authors[author][key] = _scalar(v)
                else:
                    authors[author][key] = []
    return authors


if __name__ == "__main__":
    data = load()
    for arg in sys.argv[1:]:
        data = data[arg]
    print(json.dumps(data, indent=2, ensure_ascii=False))
