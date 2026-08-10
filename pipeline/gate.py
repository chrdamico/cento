"""Phase 2: the verbatim gate — Python port of reference/verbatim_gate.sh.

Every sentence of a candidate text is searched back into the author's corpus:

  VERBATIM  found character-for-character (after normalization) in one work
  TWEAKED   found after trimming up to 3 words off either end; what remains
            must still be >= 60% of the sentence
  GLUE      not found, but short enough (<= GLUE_MAX_WORDS words) to be a
            connective the prompt allows
  NEW       not found and too long to be glue — the model wrote prose

A candidate passes only if it has no NEW sentences and at most
max(1, (100-VERBATIM_MIN)%) GLUE ones — plus two guards the shell gate never
needed (an oeuvre is large enough to cheat inside):

  excerpt guard   more than EXCERPT_MAX_RUN consecutive sentences resolved to
                  the same source paragraph = a quotation, not a cento
  range guard     fewer than MIN_WORKS distinct works cited = not a cento

The per-sentence classification carries precise locators (work, paragraph,
sentence, Gutenberg URL) and doubles as the site's hover data.

CLI:    python3 gate.py --author poe [--kind story] [--json out.json] body.txt
        exit 0 = pass, 1 = fail (report on stdout either way)
Module: load_index(author); run_gate(body_text, index, kind) -> result dict
"""

import argparse
import bisect
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textsplit import norm, split_sentences

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(ROOT, "corpus", "index")

VERBATIM_MIN = int(os.environ.get("VERBATIM_MIN", "85"))
GLUE_MAX_WORDS = int(os.environ.get("GLUE_MAX_WORDS", "12"))
EXCERPT_MAX_RUN = int(os.environ.get("EXCERPT_MAX_RUN", "3"))
MIN_WORKS = os.environ.get("MIN_WORKS")          # default depends on kind

_MD_DECOR = re.compile(r"^\s*(#+|[-*>]|\d+\.)\s+")


class Index:
    """The author's corpus, arranged for fast substring search with
    offset->locator recovery."""

    def __init__(self, records):
        self.by_norm = {}                # exact sentence norm -> record
        self.paras = {}                  # para key -> dict with joined norm
        order = []
        for r in records:
            self.by_norm.setdefault(r["norm"], r)
            pkey = r["id"].rsplit("/s", 1)[0]      # poe/<work>/p012
            if pkey not in self.paras:
                self.paras[pkey] = {"records": [], "norm": None, "offsets": None}
                order.append(pkey)
            self.paras[pkey]["records"].append(r)
        for pkey in order:
            p = self.paras[pkey]
            offsets, pos, parts = [], 0, []
            for r in p["records"]:
                offsets.append(pos)
                parts.append(r["norm"])
                pos += len(r["norm"]) + 1          # +1 for the joining space
            p["norm"] = " ".join(parts)
            p["offsets"] = offsets

    def find(self, s):
        """Locate normalized string s in the corpus.
        Returns the record of the first sentence the match touches, or None."""
        r = self.by_norm.get(s)
        if r is not None:
            return r
        for p in self.paras.values():
            off = p["norm"].find(s)
            if off >= 0:
                i = bisect.bisect_right(p["offsets"], off) - 1
                return p["records"][max(i, 0)]
        return None


def load_index(author):
    path = os.path.join(INDEX_DIR, f"{author}.jsonl")
    with open(path, encoding="utf-8") as f:
        return Index([json.loads(l) for l in f])


def _tweaked_find(index, s):
    """Seam trims: drop up to 3 words from either end; accept if what remains
    is still >= 60% of the sentence and >= 3 words, and is found verbatim."""
    words = s.split(" ")
    n = len(words)
    for a in range(0, 4):
        for b in range(0, 4):
            if a + b == 0 or n - a - b < 3:
                continue
            core = " ".join(words[a:n - b])
            if len(core) >= 0.6 * len(s):
                r = index.find(core)
                if r is not None:
                    return r
    return None


def run_gate(body_text, index, kind="story"):
    min_works = int(MIN_WORKS) if MIN_WORKS else (3 if kind == "essay" else 2)

    if kind == "poem":
        # verse: the unit is the LINE, exactly as the index stores it —
        # never resplit or rejoin, a line is a line
        sentences = [s for s in
                     (_MD_DECOR.sub("", l).strip() for l in body_text.splitlines())
                     if s]
    else:
        body = " ".join(_MD_DECOR.sub("", l) for l in body_text.splitlines())
        sentences = split_sentences(body)

    # Verse lines are short — at the prose glue width (12 words) an invented
    # line would pass as GLUE, so poems get a far tighter allowance.
    glue_max_words = 6 if kind == "poem" else GLUE_MAX_WORDS

    results = []          # one entry per sentence, in candidate order
    counts = {"VERBATIM": 0, "TWEAKED": 0, "GLUE": 0, "NEW": 0}
    for sent in sentences:
        s = norm(sent)
        if len(s) < 16:
            # too short to judge; free either way (matches the awk gate) —
            # kept in the output so the site can still render it
            results.append({"text": sent, "class": "FREE"})
            continue
        r = index.find(s)
        cls = None
        if r is not None:
            cls = "VERBATIM"
        else:
            r = _tweaked_find(index, s)
            if r is not None:
                cls = "TWEAKED"
            elif len(s.split(" ")) <= glue_max_words:
                cls = "GLUE"
            else:
                cls = "NEW"
        counts[cls] += 1
        entry = {"text": sent, "class": cls}
        if r is not None:
            entry.update({
                "src": r["id"],
                "work": r["work"],
                "work_id": r["work_id"],
                "section": r["section"],
                "para": r["para"],
                "gutenberg_url": r["gutenberg_url"],
            })
        results.append(entry)

    counted = sum(counts.values())
    allowed_glue = max(1, counted * (100 - VERBATIM_MIN) // 100)
    if kind == "poem":
        allowed_glue = 1               # one connective line, never more
    reasons = []
    if counted == 0:
        reasons.append("empty candidate: no sentences long enough to judge")
    if counts["NEW"] > 0:
        reasons.append(f"{counts['NEW']} NEW sentence(s): the model wrote prose")
    if counts["GLUE"] > allowed_glue:
        reasons.append(f"{counts['GLUE']} GLUE sentences (max {allowed_glue})")

    # excerpt guard: longest run of consecutive sourced sentences resolved to
    # the same source paragraph (GLUE/FREE between them does not reset it —
    # padding a quotation with connectives must not launder it)
    longest, run, prev_para = 0, 0, None
    for e in results:
        if e["class"] in ("VERBATIM", "TWEAKED"):
            pkey = e["src"].rsplit("/s", 1)[0]
            run = run + 1 if pkey == prev_para else 1
            prev_para = pkey
            longest = max(longest, run)
    if longest > EXCERPT_MAX_RUN:
        reasons.append(
            f"excerpt guard: {longest} consecutive sentences from one source "
            f"paragraph (max {EXCERPT_MAX_RUN}) — a quotation, not a cento")

    works = {e["work"] for e in results if e["class"] in ("VERBATIM", "TWEAKED")}
    if counted and len(works) < min_works:
        reasons.append(f"range guard: {len(works)} distinct work(s) cited, "
                       f"need >= {min_works}")

    return {
        "pass": not reasons,
        "counts": counts,
        "counted": counted,
        "allowed_glue": allowed_glue,
        "works": sorted(works),
        "max_para_run": longest,
        "min_works": min_works,
        "reasons": reasons,
        "sentences": results,
    }


def report(result):
    """Human-readable report, same spirit as the awk gate's stdout."""
    lines = []
    for e in result["sentences"]:
        if e["class"] == "FREE":
            continue
        src = f" [{e['src']}]" if "src" in e else ""
        lines.append(f"- {e['class']:8s}{src} {e['text']}")
    c = result["counts"]
    verdict = "PASS" if result["pass"] else "FAIL"
    lines.append("")
    lines.append(
        f"gate: {verdict} — {c['VERBATIM']} verbatim, {c['TWEAKED']} tweaked, "
        f"{c['GLUE']} glue (max {result['allowed_glue']}), {c['NEW']} new "
        f"of {result['counted']} sentences; {len(result['works'])} work(s), "
        f"longest same-paragraph run {result['max_para_run']}")
    for r in result["reasons"]:
        lines.append(f"  FAIL: {r}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True)
    ap.add_argument("--kind", default="story",
                    choices=("story", "essay", "poem"))
    ap.add_argument("--json", help="write full result JSON here")
    ap.add_argument("body", help="candidate body file, or - for stdin")
    args = ap.parse_args()

    body = sys.stdin.read() if args.body == "-" else \
        open(args.body, encoding="utf-8").read()
    result = run_gate(body, load_index(args.author), args.kind)
    print(report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
