# cento — implementation plan

A website that publishes new texts by dead writers — assembled, never written.
Each text is a **cento**: every sentence is copied verbatim from the author's
public-domain work, selected and reordered by an LLM, with the arrangement
checked mechanically. On the site, hovering any sentence shows exactly where it
came from (work, section, paragraph) and links to the original.

The pitch is the opposite of "AI writes like Nietzsche": *the author wrote
every word of this; the machine only found the arrangement.* Provenance is not
a footnote — it is the product. Each piece doubles as a reading map back into
the real work.

This is a spinoff of `../blog-pipeline`, which does the same thing for
Christian's own voice notes ("stitch-only posts"). The core insight transfers:
voice is guaranteed by construction when you only recombine, and the guarantee
is worthless unless it is *enforced* by a gate, not requested in a prompt.

## v1 goal

A locally served website with **two authors, two texts each**:

- **Edgar Allan Poe** — the short-story/atmosphere seat. Expect flash-length
  mood pieces (~300–800 words), not plotted stories: atmosphere stitches,
  causality doesn't.
- **Ralph Waldo Emerson** — the essayist seat. Expect real essays
  (~400–1,200 words); aphoristic corpora stitch best, and Emerson circles the
  same ideas across decades of essays, so cross-work convergence is real.

Every sentence hoverable → tooltip with source (work, section, ¶) and a link
to the Project Gutenberg original. Runs on this machine; deployment is a later
phase.

## What is taken from blog-pipeline (and what changes)

| Inherited | From | Change here |
|---|---|---|
| Verbatim gate semantics: every sentence classified VERBATIM / TWEAKED / GLUE / NEW; pass = zero NEW, glue ≤ max(1, (100−VERBATIM_MIN)%) | `bin/suggest.sh:247` (copy in `reference/verbatim_gate.sh`) | Port awk → Python. 19th-century prose needs abbreviation-aware sentence splitting (Mr., Mrs., St., etc.); awk's `[.!?] ` splitter is not enough. Gate output becomes the hover data, so it must carry precise locators, not just note ids. |
| TWEAKED rule: trim ≤3 words off either end, ≥60% of the sentence must remain and match verbatim | same | unchanged |
| Defaults: `VERBATIM_MIN=85`, `GLUE_MAX_WORDS=12` | same | unchanged to start |
| `claude -p` invocation: subscription auth (no API key), prompt+input as ONE delimited stdin stream, `--disallowedTools` for all FS/exec tools, run from `work/` | `bin/process.sh:174` (`claude_transform`) | unchanged — this pattern was debugged the hard way, keep it |
| Gate-feedback retry loop: rejected candidates fed back to the next generation call as an error log | `suggest.sh` GATE FEEDBACK block | becomes an in-run retry (up to 3 attempts per text) instead of a cross-day log |
| Prompt DNA: "stitching, not writing", glue-is-the-exception, seam trims only, permission to return nothing, sources named or the piece is invented | `prompts/suggest.md` (copy in `reference/`) | adapted per genre → `prompts/stitch-essay.md`, `prompts/stitch-story.md` |
| Model split: cheap model for mechanical steps, strongest model for the judgment call | process.sh/suggest.sh | stitching is the hard task → Fable; corpus prep is pure code, no LLM at all |
| Provenance as first-class artifact | `Posts/.provenance/` | promoted from laptop-only report to the site's main feature |

**Dropped:** anonymization (public authors), the pool/curator/retention machinery
(v1 has fixed texts; a daily rotation is Phase 5), Syncthing/phone loop,
convergence-of-notes requirement (replaced by a per-text *theme*).

**New problems blog-pipeline never had:**

1. **Corpus ≫ context.** An oeuvre is millions of words; blog-pipeline's
   `CORPUS_MAX` trick (150k chars, newest+sample) becomes a real retrieval
   step: theme → working set of whole paragraphs, ~100k chars.
2. **Fiction coherence.** Plot state doesn't stitch. Mitigations: story prompt
   demands one narrator, one tense, no character names (or one, used
   consistently), no dialogue; working-set builder prefers paragraphs without
   quoted dialogue.
3. **Excerpt degeneracy.** With a huge corpus the cheapest way to pass the gate
   is to copy one contiguous passage — that's an excerpt, not a cento. Gate
   gains an **excerpt guard**: max 3 consecutive sentences from the same source
   paragraph, and ≥2 distinct works per text (essay: ≥3).

## Architecture

```
Gutenberg ──fetch──▶ corpus/raw/ ──strip+segment──▶ corpus/index/<author>.jsonl
                                                          │  (sentence records with locators)
     theme ──────────▶ workingset.py ◀────────────────────┘
                            │  ~100k chars of whole paragraphs, ### SOURCE id= markers
                            ▼
                romantic ─▶ stitch.py ── claude -p (Fable, tools denied) ─▶ candidate
                            │                    ▲
                            ▼                    │ gate report on failure (≤3 attempts)
                        gate.py ─────────────────┘
                            │ pass
                            ▼
                texts/<author>/<slug>.json   (title, sentences[], classes, locators)
                            │
                            ▼
                site/build.py ─▶ site/out/  ── python -m http.server
```

Everything below `stitch.py` is deterministic code; the LLM appears in exactly
one place, and its output is never trusted — the gate decides.

## Repo layout

```
cento/
├── PLAN.md  README.md  .gitignore
├── prompts/
│   ├── stitch-essay.md      # adapted from blog-pipeline suggest.md
│   └── stitch-story.md      # fiction variant: mood piece, coherence rules
├── reference/               # taken verbatim from blog-pipeline, read-only
│   ├── verbatim_gate.sh     # the awk gate this project ports
│   └── blog-pipeline-suggest.md
├── bin/
│   ├── fetch_corpus.sh      # Phase 1: download + strip Gutenberg texts
│   ├── generate.sh          # Phase 3: theme → gated text (one author, one kind)
│   └── serve.sh             # Phase 4: build + http.server
├── pipeline/
│   ├── segment.py           # Phase 1: works → sentence index (JSONL)
│   ├── workingset.py        # Phase 3: theme → ~100k-char paragraph selection
│   ├── stitch.py            # Phase 3: claude -p call + retry loop
│   └── gate.py              # Phase 2: the port; also emits provenance JSON
├── site/
│   └── build.py + template  # Phase 4: texts/*.json → static HTML
├── texts/                   # generated, gated texts — committed (the product)
├── authors.yaml             # per-author: PG book ids, kind, theme list
└── corpus/  work/  logs/    # gitignored (refetchable / scratch)
```

Stack: **Python 3 stdlib** for the pipeline (no framework, no deps beyond
`claude` CLI already installed), **static HTML + CSS** for the site (hover
tooltips are pure CSS), `python -m http.server` to serve. Nothing to install,
nothing to keep running.

## Data model

`corpus/index/<author>.jsonl` — one record per sentence:

```json
{"id": "poe/usher/p012/s003", "work": "The Fall of the House of Usher",
 "work_id": "pg2148", "section": null, "para": 12, "sent": 3,
 "text": "…exact original text…", "norm": "…normalized…",
 "gutenberg_url": "https://www.gutenberg.org/ebooks/2148"}
```

`texts/<author>/<slug>.json` — the gated product:

```json
{"author": "poe", "kind": "story", "title": "…", "theme": "…",
 "created": "2026-08-09", "gate": {"verbatim": 31, "tweaked": 3, "glue": 2, "new": 0},
 "sentences": [
   {"text": "…", "class": "VERBATIM", "src": "poe/usher/p012/s003",
    "work": "The Fall of the House of Usher", "para": 12},
   {"text": "and yet,", "class": "GLUE"}
 ]}
```

Normalization (both sides, identical — port of awk `norm()`): straighten curly
quotes, collapse whitespace, lowercase. Matching is `substring in
normalized-work-text`, exactly like the original gate; the locator is recovered
by mapping the match offset back to the sentence index.

## Phases

### Phase 0 — skeleton  *(this commit)*
Repo, plan, adapted prompts, reference copies.

### Phase 1 — corpus
`bin/fetch_corpus.sh` + `pipeline/segment.py`. Download the plain-text UTF-8
files from Gutenberg into `corpus/raw/` (cached; polite — one fetch ever),
strip the `*** START/END OF THE PROJECT GUTENBERG EBOOK ***` boilerplate,
split into works/sections/paragraphs/sentences, write the JSONL index.

- Sources (verify IDs at fetch time — the script must grep the downloaded
  title and fail loudly on mismatch): Poe, *The Works of E.A. Poe, Raven
  Edition* vols 1–5 (PG #2147–2151, tales volumes first); Emerson, *Essays,
  First and Second Series* (PG catalog search at fetch time).
- Sentence splitter: regex with an abbreviation list (Mr., Mrs., Dr., St.,
  vol., etc.), never split inside quotes mid-sentence. This splitter is shared
  with the gate — one implementation, imported by both.
- **Accept when:** index exists for both authors; 20 random records spot-check
  clean (no boilerplate, sane sentence boundaries, correct work titles).

### Phase 2 — gate port
`pipeline/gate.py`, semantics from `reference/verbatim_gate.sh` plus the
excerpt guard. Test it before any LLM is involved:

- a hand-stitched paragraph of real Poe sentences → PASS, correct locators;
- the same paragraph with one sentence lightly paraphrased → FAIL (NEW);
- a contiguous excerpt of one Poe paragraph → FAIL (excerpt guard);
- seam-trimmed sentence (3 words dropped) → TWEAKED, not NEW.
- **Accept when:** those four tests pass; gate runs over the full multi-MB
  corpus in seconds.

### Phase 3 — stitcher
`pipeline/workingset.py` + `pipeline/stitch.py` + `bin/generate.sh`.

- Theme comes from `authors.yaml` (a short curated list per author — e.g. Poe:
  "the sea at night", "premature burial"; Emerson: "self-trust",
  "compensation"). Working set: score paragraphs by theme-keyword overlap,
  take whole paragraphs from ≥4 works, ~100k chars, `### SOURCE id=` markers.
- Claude call copies `claude_transform` from `process.sh:174` verbatim in
  spirit: one delimited stdin stream, `--output-format text`, all FS/exec
  tools denied, run from `work/`, model `claude-fable-5`.
- On gate FAIL: re-call with the gate report appended as GATE FEEDBACK
  (blog-pipeline's trick, in-run), max 3 attempts, then give up loudly.
- **Accept when:** `bin/generate.sh poe && bin/generate.sh emerson` twice each
  → 4 files in `texts/` that pass the gate, read coherently, and cite ≥2 works.

### Phase 4 — site
`site/build.py` renders `texts/*.json` → `site/out/`: an index page (two
authors, two texts each) and one page per text. Each sentence is a
`<span data-work data-para>`; pure-CSS tooltip shows *"The Fall of the House
of Usher, ¶12"* with a Gutenberg link. **Glue is visibly marked** (dotted
underline, tooltip says "connective — not the author's words") — the honesty
of the gate carried into the UI. `bin/serve.sh` = build + `http.server`.

- **Accept when:** `bin/serve.sh` → localhost page, hover works on every
  sentence, glue distinguishable, no JS required (or minimal, for tooltip
  positioning only).

### Phase 5 — later (not v1)
Daily generation timer (systemd user unit, pattern in blog-pipeline
`watcher/`), more authors, a curator that judges each author's pool *as a set*
(port `prompts/curate.md`), theme rotation, public deployment (static hosting
— the site is just files), per-jurisdiction public-domain cutoffs
(life+70 EU / pre-1930 US), translations (translator copyright is the trap:
the *translation* must be PD, not just the author).

## Config knobs (env, like blog-pipeline)

`VERBATIM_MIN` (85) · `GLUE_MAX_WORDS` (12) · `EXCERPT_MAX_RUN` (3, consecutive
sentences from one paragraph) · `MIN_WORKS` (2 story / 3 essay) ·
`WORKINGSET_MAX` (100000 chars) · `CLAUDE_BIN` / `CLAUDE_MODEL`
(claude-fable-5) · `ATTEMPTS` (3).

## Known risks, stated up front

- **Poe may disappoint.** Fiction is the hard seat; if flash pieces don't
  gate-pass coherently, the fallback is Poe's *essays and criticism* (same
  corpus, essayist treatment) or swapping the seat to a diarist (Pepys).
- **Sentence splitting is the quiet failure mode.** A bad split poisons both
  the index and the gate. That's why Phase 1 has a manual spot-check and the
  splitter is shared code.
- **The gate can pass a boring text.** Verbatim ≠ good. v1 accepts human
  curation (generate a few, keep the best two per author); the curator prompt
  is the Phase 5 answer, already written in blog-pipeline.
