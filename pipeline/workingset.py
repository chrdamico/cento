"""Phase 3a: theme -> working set for the stitcher.

An oeuvre is millions of characters; the model gets ~WORKINGSET_MAX (100k).
This selects *whole paragraphs* from the sentence index, scored by
theme-keyword overlap, and renders them with `### SOURCE id=` markers — the
same paragraph ids the gate will later resolve matches back to.

Selection rules (from PLAN.md):
  - whole paragraphs only — a truncated paragraph would offer the model
    sentences the gate can verify but the reader can't trace cleanly;
  - spread across works: per-work budget of WORKINGSET_MAX/4 chars, so the
    set always offers the >= 4 works a cento needs to range over;
  - story kind demotes paragraphs containing quoted dialogue (quoted speech
    drags its scene along with it — see prompts/stitch-story.md);
  - after the theme-scored paragraphs, remaining budget is filled round-robin
    across works, so the model also gets neutral connective material.

Everything is deterministic: same index + same theme = same working set.

CLI:    python3 workingset.py --author poe --theme "the sea at night"
Module: build(author, theme, kind, max_chars) -> str
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import authors as authors_mod

ROOT = authors_mod.ROOT
INDEX_DIR = os.path.join(ROOT, "corpus", "index")

WORKINGSET_MAX = int(os.environ.get("WORKINGSET_MAX", "100000"))
MIN_PARA_CHARS = 80          # fragments below this aren't worth a slot

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by", "for",
    "with", "that", "this", "these", "those", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "as", "from", "into", "not", "no",
    "should", "would", "could", "there", "here", "when", "where", "who",
    "whom", "what", "which", "how", "why", "after", "before", "between",
    "against", "without", "within",
}


def _stem(w):
    for suf in ("ing", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _kw_match(tok, kw):
    """Stemmed equality, or prefix containment for longer stems — catches
    burial/buried, remember/remembrance without a real stemmer."""
    if tok == kw:
        return True
    return len(tok) >= 4 and len(kw) >= 4 and \
        (tok.startswith(kw) or kw.startswith(tok))


def theme_keywords(theme):
    words = re.findall(r"[a-z]+", theme.lower())
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) >= 3]


def load_paragraphs(author, kind="story"):
    """Index records grouped back into paragraphs (stanzas, for verse),
    in book order. Verse keeps its line breaks — a line is a line."""
    path = os.path.join(INDEX_DIR, f"{author}.jsonl")
    joiner = "\n" if kind == "poem" else " "
    paras, order = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            pkey = r["id"].rsplit("/s", 1)[0]
            if pkey not in paras:
                paras[pkey] = {"id": pkey, "work": r["work"],
                               "para": r["para"], "texts": [], "norms": []}
                order.append(pkey)
            paras[pkey]["texts"].append(r["text"])
            paras[pkey]["norms"].append(r["norm"])
    out = []
    for pkey in order:
        p = paras[pkey]
        p["text"] = joiner.join(p["texts"])
        p["norm"] = " ".join(p["norms"])
        p["dialogue"] = '"' in p["norm"]
        del p["texts"], p["norms"]
        out.append(p)
    return out


def _score(p, kws):
    toks = [_stem(t) for t in re.findall(r"[a-z]+", p["norm"])]
    per_kw = [sum(1 for t in toks if _kw_match(t, k)) for k in kws]
    distinct = sum(1 for c in per_kw if c)
    # distinct keywords dominate; raw hits capped so one obsessive paragraph
    # doesn't crowd out coverage
    return distinct * 100 + min(sum(per_kw), 20)


def select(paras, theme, kind, max_chars):
    kws = theme_keywords(theme)
    min_chars = 40 if kind == "poem" else MIN_PARA_CHARS   # stanzas run short
    pool = [p for p in paras if len(p["text"]) >= min_chars]
    for p in pool:
        p["score"] = _score(p, kws) if kws else 0

    demote = (lambda p: p["dialogue"]) if kind == "story" else (lambda p: False)
    themed = sorted((p for p in pool if p["score"] > 0 and not demote(p)),
                    key=lambda p: (-p["score"], p["id"]))

    # filler, round-robin across works in book order: preferred material
    # first, demoted dialogue last
    rest = [p for p in pool if p not in themed]
    by_work = {}
    for p in rest:
        by_work.setdefault(p["work"], []).append(p)
    for plist in by_work.values():
        plist.sort(key=lambda p: (demote(p), -p["score"], p["para"]))
    filler, robin = [], list(by_work.values())
    while robin:
        robin = [pl for pl in robin if pl]
        for pl in robin:
            if pl:
                filler.append(pl.pop(0))

    work_cap = max_chars // 4
    used, total, picked = {}, 0, []
    for p in themed + filler:
        n = len(p["text"])
        if total + n > max_chars or used.get(p["work"], 0) + n > work_cap:
            continue
        picked.append(p)
        used[p["work"]] = used.get(p["work"], 0) + n
        total += n

    # render grouped by work (order of first appearance in the ranking),
    # original paragraph order within a work — reads as material, not noise
    work_order = []
    for p in picked:
        if p["work"] not in work_order:
            work_order.append(p["work"])
    picked.sort(key=lambda p: (work_order.index(p["work"]), p["para"]))
    return picked, used


def build(author, theme, kind, max_chars=WORKINGSET_MAX):
    picked, used = select(load_paragraphs(author, kind), theme, kind, max_chars)
    if len(used) < 4:
        print(f"workingset: WARNING only {len(used)} work(s) in set",
              file=sys.stderr)
    blocks = [f"### SOURCE id={p['id']}\n{p['text']}" for p in picked]
    print(f"workingset: {sum(used.values())} chars, {len(picked)} paragraphs, "
          f"{len(used)} works", file=sys.stderr)
    return "\n\n".join(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--kind", choices=("story", "essay", "poem"))
    ap.add_argument("--max", type=int, default=WORKINGSET_MAX)
    args = ap.parse_args()
    kind = args.kind or authors_mod.load()[args.author]["kind"]
    print(build(args.author, args.theme, kind, args.max))


if __name__ == "__main__":
    main()
