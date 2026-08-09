"""Shared text utilities: normalization and sentence splitting.

This module is imported by BOTH segment.py (index build) and gate.py
(verification). One implementation on purpose — a splitter mismatch between
the two sides is the quiet failure mode named in PLAN.md.

norm() is a faithful port of the awk norm() in reference/verbatim_gate.sh:
straighten curly quotes, collapse whitespace, lowercase. Matching is
substring-in-normalized-text, so both sides must normalize identically.
"""

import re

# Words whose trailing period does not end a sentence. 19th-century prose is
# dense with these; the awk gate's bare `[.!?] ` splitter was not enough.
ABBREVS = {
    "mr", "mrs", "dr", "st", "ms", "messrs", "mme", "mlle", "prof", "rev",
    "hon", "esq", "sr", "jr", "gen", "col", "capt", "maj", "lieut", "sergt",
    # NB: never add entries here that are common English words in their own
    # right ("art", "sec", "fig") — a sentence legitimately ending in one
    # would silently glue onto its successor.
    "vol", "vols", "ch", "chap", "no", "nos", "pp",
    "cf", "viz", "eg", "ie", "e.g", "i.e", "etc",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "oct", "nov", "dec",
}

_SENT_END = re.compile(r'[.!?…]+[”’"\'\)\]]*\s+')
_LAST_WORD = re.compile(r'([\w’\'.\-]+?)\.?[.!?…]*[”’"\'\)\]]*$')


def norm(s):
    """Normalize for matching — must equal the awk gate's norm()."""
    s = s.replace("‘", "'").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _protects(prev, nxt):
    """True if the boundary after `prev` must NOT split."""
    if nxt[:1].islower():
        return True                       # mid-sentence continuation
    m = _LAST_WORD.search(prev)
    word = (m.group(1) if m else "").lower().rstrip(".")
    if not word:
        return False
    if prev.rstrip()[-1:] in "!?…":
        return False                      # ! ? always end regardless of word
    if len(word) == 1 and word.isalpha():
        return True                       # an initial: "A. Gordon Pym"
    if "." in word:
        return True                       # multi-initial: "h.l", "i.e"
    if word in ABBREVS:
        if word in ("no", "nos", "vol", "vols", "ch", "chap", "pp"):
            return nxt[:1].isdigit()      # "No. 7" yes, "No. He said" no
        return True
    return False


def split_sentences(text):
    """Split a paragraph (whitespace already collapsed OK) into sentences."""
    text = re.sub(r"\s+", " ", text).strip()
    out, start = [], 0
    for m in _SENT_END.finditer(text):
        candidate = text[start:m.end()].rstrip()
        nxt = text[m.end():]
        if _protects(candidate, nxt):
            continue
        out.append(candidate)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out
