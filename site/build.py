"""Phase 4: texts/<author>/<slug>.json -> site/out/ — static HTML, no JS.

Each sentence becomes a <span> whose pure-CSS tooltip shows the locator the
gate resolved (work, paragraph, Gutenberg link). Glue and unverifiable
fragments are visibly marked — the honesty of the gate carried into the UI.
The index page opens with the manifesto from site/about.md.

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


# The one permitted piece of JS (PLAN Phase 4): tooltip positioning only.
# A tooltip anchored near the right edge would clip off-screen; flip it.
FLIP_JS = """<script>
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
</script>"""


def page(title, body, css_prefix=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="{css_prefix}style.css">
<main>
{body}
</main>
{FLIP_JS}
</html>
"""


def sentence_html(e):
    cls = e["class"].lower()
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


def text_paragraphs(sentences):
    paras, cur = [], []
    for e in sentences:
        if e.get("pbreak") and cur:
            paras.append(cur)
            cur = []
        cur.append(e)
    if cur:
        paras.append(cur)
    return "\n".join(
        "<p>" + "\n".join(sentence_html(e) for e in p) + "</p>"
        for p in paras)


def text_page(rec):
    g = rec["gate"]
    n_src = g["VERBATIM"] + g["TWEAKED"]
    gate_bits = [f"{n_src} sentences found verbatim in {esc(rec['author_name'])}"]
    if g["TWEAKED"]:
        gate_bits.append(f"{g['TWEAKED']} of them trimmed at a seam")
    if g["GLUE"]:
        gate_bits.append(f"{g['GLUE']} connective{'s' if g['GLUE'] > 1 else ''} "
                         f"added (dotted)")
    works = ", ".join(esc(w) for w in rec["works"])
    body = f"""<p class="byline site-title"><a href="../index.html">cento</a></p>
<h1>{esc(rec['title'])}</h1>
<p class="byline">{esc(rec['author_name'])} &mdash; arranged, never written
&middot; {esc(rec['created'])} &middot; hover any sentence for its source</p>
<div class="piece">
{text_paragraphs(rec['sentences'])}
</div>
<p class="gateline">{"; ".join(gate_bits)} &mdash; checked mechanically,
not on trust. Gathered from: {works}.
<a href="../index.html#about">How this works.</a></p>
"""
    return page(f"{rec['title']} — {rec['author_name']}", body, "../")


def index_page(cfg, by_author):
    with open(os.path.join(SITE, "about.md"), encoding="utf-8") as f:
        manifesto = md_paragraphs(f.read())
    sections = []
    for author, meta in cfg.items():
        items = []
        for slug, rec in sorted(by_author.get(author, []),
                                key=lambda sr: (sr[1]["created"], sr[0])):
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
    body = f"""<h1 class="site-title">cento</h1>
<p class="tagline">new texts by dead writers &mdash; assembled, never written</p>
{sections_html}<hr>
<div class="manifesto" id="about">
{manifesto}
</div>
"""
    return page("cento — new texts by dead writers", body)


def main():
    cfg = authors_mod.load()
    by_author = {}
    for author in cfg:
        adir = os.path.join(TEXTS, author)
        if not os.path.isdir(adir):
            continue
        for fn in sorted(os.listdir(adir)):
            if fn.endswith(".json"):
                with open(os.path.join(adir, fn), encoding="utf-8") as f:
                    by_author.setdefault(author, []).append(
                        (fn[:-5], json.load(f)))

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    shutil.copy(os.path.join(SITE, "style.css"), OUT)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page(cfg, by_author))
    n = 0
    for author, texts in by_author.items():
        os.makedirs(os.path.join(OUT, author), exist_ok=True)
        for slug, rec in texts:
            path = os.path.join(OUT, author, f"{slug}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text_page(rec))
            n += 1
    print(f"site: index + {n} text page(s) -> {OUT}")


if __name__ == "__main__":
    main()
