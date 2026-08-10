"""Phase 1b: corpus/raw/<author>/pg<id>.txt -> corpus/index/<author>.jsonl

One record per sentence, with a locator precise enough to power the site's
hover tooltips:

  {"id": "poe/the-gold-bug/p012/s003", "work": "The Gold-Bug",
   "work_id": "pg2148", "section": null, "para": 12, "sent": 3,
   "text": "...original...", "norm": "...normalized...",
   "gutenberg_url": "https://www.gutenberg.org/ebooks/2148"}

Only the author's own words enter the index. Both books carry non-author
matter — Poe's Raven Edition opens with a biography and carries
Griswold/redactor endnotes; the Emerson volume is a 1907 school edition whose
introduction and NOTES are the editor's (Edna Turpin), not Emerson's. Works
are recognized from the Contents listing; a blocklist drops the non-author
sections; footnote blocks and editorial markers are stripped.
"""

import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import authors as authors_mod
from textsplit import norm, split_sentences

ROOT = authors_mod.ROOT
RAW = os.path.join(ROOT, "corpus", "raw")
INDEX = os.path.join(ROOT, "corpus", "index")

# Sections that are not the author's prose. Matched against normalized
# headings from the Contents listing and the body.
NON_AUTHOR = re.compile(
    r"^(PREFACE|LIFE OF|DEATH OF|INTRODUCTION|CRITICAL OPINIONS"
    r"|CHRONOLOGICAL|NOTES\b|AN APPRECIATION|PUBLISHERS"
    # Zarathustra: the Forster-Nietzsche biography, part dividers, and the
    # appendix; BGE: the closing poem is L.A. Magnus's translation, not
    # Zimmern's prose
    r"|HOW ZARATHUSTRA CAME INTO BEING|APPENDIX"
    r"|(FIRST|SECOND|THIRD|FOURTH) PART|FROM THE HEIGHTS)"
)

# Books whose Contents entries are chapters/discourses of one work: the
# entry alone ("The Free Spirit") makes a poor hover title, so the book
# title is prefixed ("Beyond Good and Evil: The Free Spirit").
WORK_PREFIX = {
    1998: "Thus Spake Zarathustra",
    4363: "Beyond Good and Evil",
}
# Leading chapter/discourse numbering stripped from those entries.
ENTRY_NUMBER = re.compile(r"^(CHAPTER\s+)?[IVXLC]+[.:]\s*", re.IGNORECASE)
CHAPTER = re.compile(r"^CHAPTER\s+(\d+)")
FOOTNOTE_HEAD = re.compile(r"^FOOTNOTES?\b", re.IGNORECASE)
# Editorial reference marks stripped from body text: [93], (*1), {*2}
MARKERS = re.compile(r"\[\d+\]|\(\*\d+\)|\{\*\d+\}")


def heading_key(s):
    """Canonical form for matching Contents entries to body headings."""
    s = MARKERS.sub("", s)
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()
    return s


def is_capsline(s):
    """A plausible heading: short-ish line whose letters are all uppercase."""
    if not (3 < len(s) <= 70):
        return False
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def book_lines(path):
    """Lines between the PG *** START / *** END markers."""
    lines = open(path, encoding="utf-8").read().replace("\r", "").splitlines()
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith("*** START OF THE PROJECT GUTENBERG"):
            lo = i + 1
        elif l.startswith("*** END OF THE PROJECT GUTENBERG"):
            hi = i
            break
    if lo is None or hi is None:
        raise SystemExit(f"{path}: PG START/END markers not found")
    return lines[lo:hi]


def parse_contents(lines):
    """Return (entries, index_after_contents). Entries in book order.

    Two shapes exist in the corpus: ALL-CAPS entries (Poe, Emerson, BGE)
    and indented mixed-case entries with roman numerals (Zarathustra).
    Indented mixed-case lines are accepted as entries; a flush-left
    non-caps line still ends the listing (redactor notes etc.)."""
    start = None
    for i, l in enumerate(lines[:200]):
        if l.strip().upper().rstrip(".") in ("CONTENTS", "TABLE OF CONTENTS"):
            start = i + 1
            break
    if start is None:
        raise SystemExit("no Contents block found")
    entries, blanks, i = [], 0, start
    while i < len(lines):
        s = lines[i].strip()
        indent = len(lines[i]) - len(lines[i].lstrip())
        if not s:
            blanks += 1
            if blanks >= 3 and entries:
                break
        else:
            blanks = 0
            if is_capsline(s) and not CHAPTER.match(heading_key(s)):
                entries.append(s)
            elif not is_capsline(s):
                if indent >= 3 and 3 < len(s) <= 70:
                    entries.append(s)      # Zarathustra-style entry
                else:
                    break
        i += 1
    return entries, i


def match_entry(line, keys):
    """Which contents entry does this body heading correspond to, if any?"""
    k = heading_key(line)
    if not k:
        return None
    if k in keys:
        return k
    best, best_r = None, 0.0
    for key in keys:
        r = difflib.SequenceMatcher(None, k, key).ratio()
        if r > best_r:
            best, best_r = key, r
    return best if best_r >= 0.75 else None


def clean(text):
    text = MARKERS.sub("", text)
    text = text.replace("_", "")          # PG italics markers
    # aphorism numbering (BGE: "63. He who is a thorough teacher...") is
    # apparatus, not prose — the hover locator already carries the position
    text = re.sub(r"^\d{1,3}\.\s+", "", text)
    return text


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48].rstrip("-")


# The Contents listings carry a couple of warts worth fixing in the displayed
# title (they are what the hover tooltip will show).
TITLE_FIXES = {
    "william wilso": "William Wilson",            # contents typo in pg2148
    "ms. found in a bottle": "MS. Found in a Bottle",
}


def titlecase(entry):
    """Contents entries are ALL CAPS; render a readable work title."""
    small = {"a", "an", "and", "at", "but", "by", "for", "in", "into", "of",
             "on", "or", "the", "to", "with"}
    cleaned = MARKERS.sub("", entry).strip(" .")
    if cleaned.lower() in TITLE_FIXES:
        return TITLE_FIXES[cleaned.lower()]

    def cap_part(part, first):
        lp = part.lower()
        if not first and "." not in lp and lp.strip(",;:") in small:
            return lp
        return lp[:1].upper() + lp[1:]

    words = []
    for i, w in enumerate(cleaned.split()):
        # capitalize each hyphen/em-dash-separated piece: GOLD-BUG -> Gold-Bug
        w = re.sub(r"[^-—]+",
                   lambda m: cap_part(m.group(0), i == 0 and m.start() == 0), w)
        words.append(w)
    return " ".join(words)


def work_title(entry, gid):
    """Display title for a Contents entry; chapter-style books get the book
    title prefixed so hover locators read as provenance, not as riddles."""
    cleaned = ENTRY_NUMBER.sub("", MARKERS.sub("", entry).strip(" ."))
    t = titlecase(cleaned)
    prefix = WORK_PREFIX.get(gid)
    if not prefix:
        return t
    if heading_key(t) == heading_key(prefix):
        return prefix                      # the book's own title entry
    return f"{prefix}: {t}"


# A paragraph that opens with an editorial footnote definition, e.g. "(*1) ..."
FOOTNOTE_PARA = re.compile(r"^\(\*\d+\)")


def segment_book(author, gid):
    """Two passes. Pass 1 walks the body and assigns raw paragraphs to works
    using the Contents headings. Pass 2 decides, per work, which indentation
    level is running prose (the Raven Edition mixes 6-space and 0-space tales
    in one volume) and drops everything else — epigraphs, verse, block quotes,
    letters — plus footnote-definition paragraphs."""
    lines = book_lines(os.path.join(RAW, author, f"pg{gid}.txt"))
    entries, body_start = parse_contents(lines)
    keys = {}
    for e in entries:
        k = heading_key(e)
        if k and k not in keys:
            keys[k] = work_title(e, gid)
    include = {k for k in keys if not NON_AUTHOR.match(k)}

    work_key = None          # contents key of the work being collected
    section = None           # current chapter within the work, if any
    seen = set()
    paras = []               # (work_key, section, indent, [stripped lines])
    cur = []

    def flush():
        nonlocal cur
        if cur and work_key in include:
            indent = len(cur[0]) - len(cur[0].lstrip())
            paras.append((work_key, section, indent, [l.strip() for l in cur]))
        cur = []

    for line in lines[body_start:]:
        s = line.strip()
        if not s:
            flush()
            continue
        if is_capsline(s):
            m = CHAPTER.match(heading_key(s))
            if m and work_key:
                flush()
                section = f"Chapter {m.group(1)}"
                continue
            hit = match_entry(s, keys)
            if hit:
                if hit in seen:
                    # A repeat: a subtitle ("A SEQUEL TO ..."), an in-text
                    # headline, or Emerson's NOTES re-listing the essays.
                    # A display line, not prose — drop it, and whatever
                    # collection state we're in stays. (The NOTES heading
                    # itself is blocklisted and turns collection off.)
                    flush()
                    continue
                flush()
                if hit not in include:
                    work_key = None      # non-author section
                else:
                    seen.add(hit)
                    work_key = hit
                section = None
                continue
        if FOOTNOTE_HEAD.match(s):
            flush()
            work_key = None              # endnote block: off until next work
            continue
        if work_key is not None:
            cur.append(line)
    flush()

    # per-work dominant indent = the work's prose level
    from collections import Counter
    indent_hist = {}
    for wkey, _sec, indent, plines in paras:
        indent_hist.setdefault(wkey, Counter())[indent] += len(plines)
    prose_indent = {w: h.most_common(1)[0][0] for w, h in indent_hist.items()}

    records, counts = [], {}
    para_no = {}
    for wkey, sec, indent, plines in paras:
        if indent != prose_indent[wkey]:
            continue
        text = clean(" ".join(plines))
        if FOOTNOTE_PARA.match(text) or not text.strip():
            continue
        title = keys[wkey]
        para_no[wkey] = para_no.get(wkey, 0) + 1
        sents = [s for s in split_sentences(text) if any(c.isalpha() for c in s)]
        for si, sent in enumerate(sents, 1):
            records.append({
                "id": f"{author}/{slugify(title)}/p{para_no[wkey]:03d}/s{si:03d}",
                "work": title,
                "work_id": f"pg{gid}",
                "section": sec,
                "para": para_no[wkey],
                "sent": si,
                "text": sent,
                "norm": norm(sent),
                "gutenberg_url": f"https://www.gutenberg.org/ebooks/{gid}",
            })
        counts[title] = counts.get(title, 0) + len(sents)
    return records, counts


VERSE_TITLE = re.compile(r"^\S.*[a-z]")     # flush-left line with lowercase
SECTION_NO = re.compile(r"^\s+(\d{1,3})\s*$")


def segment_verse(author, gid):
    """kind: poem — Leaves of Grass shape: flush-left mixed-case poem
    titles, verse lines indented 2, wrapped continuations indented deeper,
    stanzas split on blank lines, numbered sections inside long poems.
    The unit is the LINE (the classical cento unit); stanzas take the
    paragraph slot so the excerpt guard and workingset transfer as-is."""
    lines = book_lines(os.path.join(RAW, author, f"pg{gid}.txt"))
    started = False                # nothing before the first BOOK heading
    poem = section = None
    stanza_no = line_no = 0
    seen_titles = {}
    poems = {}                     # title -> [(section, stanza, [lines])]
    cur = None                     # current stanza: list of logical lines

    def flush_stanza():
        nonlocal cur
        if poem and cur:
            poems.setdefault(poem, []).append((section, cur))
        cur = None

    for raw in lines:
        s = raw.rstrip()
        if not s.strip():
            flush_stanza()
            continue
        indent = len(s) - len(s.lstrip())
        text = s.strip()
        if indent == 0:
            if is_capsline(text):          # "BOOK I.  INSCRIPTIONS" etc.
                flush_stanza()
                started = True
                poem = None
                continue
            if started and VERSE_TITLE.match(s):
                flush_stanza()
                title = clean(text).strip(" .")
                n = seen_titles.get(title, 0) + 1
                seen_titles[title] = n
                poem = title if n == 1 else f"{title} ({n})"
                section = None
                continue
            continue                        # front matter / stray line
        if not started or poem is None:
            continue
        m = SECTION_NO.match(s)
        if m:
            flush_stanza()
            section = f"§{m.group(1)}"
            continue
        if indent >= 5 and cur and cur[-1]:
            cur[-1] = f"{cur[-1]} {clean(text)}"   # wrapped continuation
            continue
        if cur is None:
            cur = []
        cur.append(clean(text))
    flush_stanza()

    records, counts = [], {}
    for title, stanzas in poems.items():
        para_no = 0
        for sec, stanza in stanzas:
            para_no += 1
            for si, line in enumerate(stanza, 1):
                if not any(c.isalpha() for c in line):
                    continue
                records.append({
                    "id": f"{author}/{slugify(title)}/p{para_no:03d}/s{si:03d}",
                    "work": title,
                    "work_id": f"pg{gid}",
                    "section": sec,
                    "para": para_no,
                    "sent": si,
                    "text": line,
                    "norm": norm(line),
                    "gutenberg_url": f"https://www.gutenberg.org/ebooks/{gid}",
                })
                counts[title] = counts.get(title, 0) + 1
    return records, counts


def main():
    os.makedirs(INDEX, exist_ok=True)
    cfg = authors_mod.load()
    for author, meta in cfg.items():
        segment = segment_verse if meta["kind"] == "poem" else segment_book
        all_records, all_counts = [], {}
        for gid in meta["gutenberg"]:
            recs, counts = segment(author, gid)
            all_records.extend(recs)
            for t, n in counts.items():
                all_counts[t] = all_counts.get(t, 0) + n
        out = os.path.join(INDEX, f"{author}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for r in all_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{author}: {len(all_records)} sentences, "
              f"{len(all_counts)} works -> {out}")
        for t, n in sorted(all_counts.items(), key=lambda kv: -kv[1]):
            print(f"   {n:5d}  {t}")


if __name__ == "__main__":
    main()
