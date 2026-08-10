"""Phase 4/5: texts/<author>/<slug>.json -> site/out/ — static HTML, no JS
beyond tooltip positioning and tap-to-focus.

Each sentence becomes a <span> whose pure-CSS tooltip shows the locator the
gate resolved (work, paragraph, Gutenberg link). Glue and unverifiable
fragments are visibly marked; the seams toggle tints sentences by source
work. The index leads with the latest piece in full (Phase 5: the visitor
lands on content, not on a table of contents), archive and manifesto below.
Every page carries OpenGraph/Twitter meta; an Atom feed lists all pieces.

SITE_URL (env) is the deployed base URL for canonical links, og:url and the
feed; unset, absolute URLs fall back to http://localhost:8080 and a warning
is printed — fine for local reading, set it before deploying.

Run: python3 site/build.py    (or bin/serve.sh, which builds then serves)
"""

import html
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import authors as authors_mod

SITE = os.path.join(ROOT, "site")
TEXTS = os.path.join(ROOT, "texts")
OUT = os.path.join(SITE, "out")

SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
BASE = SITE_URL or "http://localhost:8080"
SITE_NAME = "cento"
TAGLINE = "new texts by dead writers — assembled, never written"

esc = html.escape


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def md_paragraphs(text):
    """about.md is deliberately plain: paragraphs, *em*, [links](url)."""
    paras = [re.sub(r"\s+", " ", p).strip()
             for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n".join(f"<p>{md_inline(p)}</p>" for p in paras if p)


# The permitted JS (PLAN Phase 4/5): tooltip positioning, plus tap-to-focus —
# iOS Safari does not focus a tabindex span on tap, so tooltips would be
# hover-only on phones without the click handler.
PAGE_JS = """<script>
document.addEventListener("mouseover", function (e) {
  var s = e.target.closest && e.target.closest(".s");
  if (!s) return;
  var tip = s.querySelector(".tip");
  if (!tip) return;
  tip.classList.remove("flip");
  if (tip.getBoundingClientRect().right >
      document.documentElement.clientWidth - 8) {
    tip.classList.add("flip");
  }
});
document.addEventListener("click", function (e) {
  var s = e.target.closest && e.target.closest(".s");
  if (s && document.activeElement !== s) s.focus({ preventScroll: true });
});
</script>"""


def head_meta(title, desc, path, has_card, prefix=""):
    """OpenGraph/Twitter meta + canonical + feed link for one page.
    path is the site-relative page path ('' for the index)."""
    url = f"{BASE}/{path}"
    lines = [
        f'<meta name="description" content="{esc(desc)}">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<link rel="canonical" href="{esc(url)}">',
        f'<link rel="alternate" type="application/atom+xml" '
        f'title="{SITE_NAME}" href="{prefix}feed.xml">',
    ]
    if has_card:
        lines += [
            f'<meta property="og:image" content="{BASE}/card.png">',
            '<meta name="twitter:card" content="summary_large_image">',
        ]
    else:
        lines.append('<meta name="twitter:card" content="summary">')
    return "\n".join(lines)


def page(title, body, css_prefix="", head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{head}
<link rel="icon" href="data:,">
<link rel="stylesheet" href="{css_prefix}style.css">
<header class="site">
<div class="inner">
<a class="wordmark" href="{css_prefix}index.html">cento</a>
<nav><a href="{css_prefix}about.html">about</a></nav>
</div>
</header>
<main>
{body}
</main>
{PAGE_JS}
</html>
"""


def sentence_html(e, work_slot):
    cls = e["class"].lower()
    slot = work_slot.get(e.get("work"))
    if slot:
        cls += f" w{slot}"
    if e["class"] in ("VERBATIM", "TWEAKED"):
        where = f'<span class="work">{esc(e["work"])}</span>'
        if e.get("section"):
            where += f', {esc(e["section"])}'
        where += f", &para;{e['para']}"
        note = ('<br><span class="note">trimmed at the seam</span>'
                if e["class"] == "TWEAKED" else "")
        tip = (f'{where} &middot; <a href="{esc(e["gutenberg_url"])}">'
               f"Gutenberg</a>{note}")
    elif e["class"] == "GLUE":
        tip = '<span class="note">connective &mdash; not the author\'s words</span>'
    else:  # FREE
        tip = '<span class="note">too short to verify</span>'
    return (f'<span class="s {cls}" tabindex="0">{esc(e["text"])}'
            f'<span class="tip">{tip}</span></span>')


def text_paragraphs(sentences, work_slot):
    paras, cur = [], []
    for e in sentences:
        if e.get("pbreak") and cur:
            paras.append(cur)
            cur = []
        cur.append(e)
    if cur:
        paras.append(cur)
    return "\n".join(
        "<p>" + "\n".join(sentence_html(e, work_slot) for e in p) + "</p>"
        for p in paras)


def legend_html(rec, work_slot):
    """Legend for the seams view — swatch + work title, identity never
    color-alone. Works past the 8 palette slots stay untinted (never cycle
    hues); glue keeps its dotted mark."""
    items = [f'<li><span class="swatch w{slot}"></span>{esc(work)}</li>'
             for work, slot in work_slot.items()]
    items.extend(f'<li><span class="swatch"></span>{esc(w)}</li>'
                 for w in rec["works"][8:])
    if any(e["class"] == "GLUE" for e in rec["sentences"]):
        items.append('<li><span class="swatch glueswatch"></span>'
                     "connective &mdash; not the author's words</li>")
    return '<ul class="legend">\n' + "\n".join(items) + "\n</ul>"


def gateline(rec, about_href, permalink=None):
    g = rec["gate"]
    n_src = g["VERBATIM"] + g["TWEAKED"]
    bits = [f"{n_src} sentences found verbatim in {esc(rec['author_name'])}"]
    if g["TWEAKED"]:
        bits.append(f"{g['TWEAKED']} of them trimmed at a seam")
    if g["GLUE"]:
        bits.append(f"{g['GLUE']} connective{'s' if g['GLUE'] > 1 else ''} "
                    f"added (dotted)")
    works = ", ".join(esc(w) for w in rec["works"])
    perma = (f' <a href="{esc(permalink)}">Permalink.</a>' if permalink else "")
    return (f'<p class="gateline">{"; ".join(bits)} &mdash; checked '
            f"mechanically, not on trust. Gathered from: {works}. "
            f'<a href="{about_href}">How this works.</a>{perma}</p>')


def piece_block(rec, about_href, permalink=None, heading="h1"):
    """The toggle + legend + sentences + gateline for one piece. The seams
    checkbox and its dependents must stay siblings (the CSS uses `~`)."""
    work_slot = {w: i + 1 for i, w in enumerate(rec["works"][:8])}
    title = esc(rec["title"])
    if permalink:
        title = f'<a href="{esc(permalink)}">{title}</a>'
    return f"""<{heading} class="piece-title">{title}</{heading}>
<section class="piece-wrap">
<input type="checkbox" id="seams" class="seams-box" checked>
<p class="byline controls">{esc(rec['author_name'])} &mdash; arranged, never
written &middot; {esc(rec['created'])} &middot; hover any sentence for its
source &middot; <label for="seams" class="seams"><span class="on">hide the
seams</span><span class="off">show the seams</span></label></p>
{legend_html(rec, work_slot)}
<div class="piece">
{text_paragraphs(rec['sentences'], work_slot)}
</div>
{gateline(rec, about_href, permalink)}
</section>"""


def excerpt(rec, limit=160):
    out = ""
    for e in rec["sentences"]:
        out = f"{out} {e['text']}".strip()
        if len(out) >= limit:
            break
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    return out


def text_desc(rec):
    return (f"{excerpt(rec)} — every sentence {rec['author_name']}'s own, "
            f"found and arranged, never written.")


def text_page(rec, path, has_card):
    body = piece_block(rec, "../about.html") + "\n"
    head = head_meta(f"{rec['title']} — {rec['author_name']}",
                     text_desc(rec), path, has_card, "../")
    return page(f"{rec['title']} — {rec['author_name']}", body, "../", head)


def about_page(has_card):
    with open(os.path.join(SITE, "about.md"), encoding="utf-8") as f:
        manifesto = md_paragraphs(f.read())
    body = f"""<h1 class="piece-title">about</h1>
<div class="manifesto">
{manifesto}
</div>
<hr>
<p>New pieces are announced on the <a href="feed.xml">Atom feed</a> &mdash;
paste that link into a feed reader (it is a machine-readable file, not a
page to visit).</p>
"""
    head = head_meta(f"about — {SITE_NAME}",
                     "What a cento is, and how every sentence on this site "
                     "is verified to be the author's own.",
                     "about.html", has_card)
    return page(f"about — {SITE_NAME}", body, "", head)


def index_page(cfg, by_author, latest, has_card):
    latest_html = ""
    if latest:
        author, slug, rec = latest
        latest_html = (
            '<p class="latest-label">the latest piece</p>\n'
            + piece_block(rec, "about.html",
                          f"{esc(author)}/{esc(slug)}.html", heading="h1")
            + "\n<hr>\n")

    sections = []
    for author, meta in cfg.items():
        items = []
        for slug, rec in sorted(by_author.get(author, []),
                                key=lambda sr: (sr[1]["created"], sr[0]),
                                reverse=True):
            items.append(
                f'<li><a href="{esc(author)}/{esc(slug)}.html">'
                f'{esc(rec["title"])}</a>'
                f'<span class="meta">{esc(rec["kind"])} &middot; gathered '
                f'from {len(rec["works"])} works &middot; '
                f'{esc(rec["created"])}</span></li>')
        if items:
            sections.append(f'<h2 class="author">{esc(meta["name"])}</h2>\n'
                            f'<ul class="texts">\n' + "\n".join(items) +
                            "\n</ul>")
    sections_html = "".join(s + "\n" for s in sections)
    body = f"""<p class="tagline">{esc(TAGLINE)} &mdash; every sentence the
author's own, verified. <a href="about.html">How this works.</a></p>
{latest_html}{sections_html}"""
    head = head_meta(f"{SITE_NAME} — {TAGLINE}",
                     "Every sentence verbatim from the author's public-domain "
                     "work, verified mechanically, traceable on hover. The "
                     "author wrote every word; the machine only found the "
                     "arrangement.",
                     "", has_card)
    return page(f"{SITE_NAME} — {TAGLINE}", body, "", head)


def plain_paragraphs(rec):
    """Feed rendering: the piece as plain <p> text, no span apparatus."""
    paras, cur = [], []
    for e in rec["sentences"]:
        if e.get("pbreak") and cur:
            paras.append(cur)
            cur = []
        cur.append(e["text"])
    if cur:
        paras.append(cur)
    return "\n".join("<p>" + esc(" ".join(p)) + "</p>" for p in paras)


def atom_feed(all_texts):
    entries = []
    newest = "1970-01-01"
    for author, slug, rec in sorted(all_texts,
                                    key=lambda t: (t[2]["created"], t[1]),
                                    reverse=True):
        url = f"{BASE}/{author}/{slug}.html"
        updated = f"{rec['created']}T12:00:00Z"
        newest = max(newest, rec["created"])
        content = (plain_paragraphs(rec)
                   + f"<p>Every sentence is {esc(rec['author_name'])}'s own, "
                   f"verified verbatim against {len(rec['works'])} works — "
                   f'<a href="{esc(url)}">sources on hover</a>.</p>')
        entries.append(f"""<entry>
<title>{esc(rec['title'])}</title>
<author><name>{esc(rec['author_name'])}</name></author>
<link href="{esc(url)}"/>
<id>{esc(url)}</id>
<updated>{updated}</updated>
<content type="html">{esc(content)}</content>
</entry>""")
    entries_xml = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>{SITE_NAME}</title>
<subtitle>{esc(TAGLINE)}</subtitle>
<link href="{BASE}/feed.xml" rel="self"/>
<link href="{BASE}/"/>
<id>{BASE}/</id>
<updated>{newest}T12:00:00Z</updated>
{entries_xml}
</feed>
"""


def main():
    cfg = authors_mod.load()
    by_author, all_texts = {}, []
    for author in cfg:
        adir = os.path.join(TEXTS, author)
        if not os.path.isdir(adir):
            continue
        for fn in sorted(os.listdir(adir)):
            if fn.endswith(".json"):
                with open(os.path.join(adir, fn), encoding="utf-8") as f:
                    rec = json.load(f)
                by_author.setdefault(author, []).append((fn[:-5], rec))
                all_texts.append((author, fn[:-5], rec))

    latest = max(all_texts, key=lambda t: (t[2]["created"], t[1]),
                 default=None)
    card_src = os.path.join(SITE, "card.png")
    has_card = os.path.exists(card_src)

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    shutil.copy(os.path.join(SITE, "style.css"), OUT)
    if has_card:
        shutil.copy(card_src, OUT)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page(cfg, by_author, latest, has_card))
    with open(os.path.join(OUT, "about.html"), "w", encoding="utf-8") as f:
        f.write(about_page(has_card))
    with open(os.path.join(OUT, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(atom_feed(all_texts))
    n = 0
    for author, slug, rec in all_texts:
        os.makedirs(os.path.join(OUT, author), exist_ok=True)
        path = f"{author}/{slug}.html"
        with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
            f.write(text_page(rec, path, has_card))
        n += 1
    if not SITE_URL:
        print("site: WARNING SITE_URL unset — canonical/og/feed URLs point "
              f"at {BASE} (fine locally, set SITE_URL before deploying)")
    print(f"site: index + {n} text page(s) + feed.xml -> {OUT}")


if __name__ == "__main__":
    main()
