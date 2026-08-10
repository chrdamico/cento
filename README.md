# cento

New texts by dead writers — assembled, never written.

Each piece is a [cento](https://en.wikipedia.org/wiki/Cento_(poetry)): every
sentence copied verbatim from an author's public-domain work, selected and
arranged by an LLM, verified mechanically by a gate that searches each sentence
back into the corpus. Hover any sentence on the site and it tells you exactly
where it came from.

Not "AI writes like Poe" — **Poe wrote every word of this; the machine only
found the arrangement.**

Spun off from [blog-pipeline](../blog-pipeline), which stitches the author's
own voice notes under the same contract. The inherited pieces (verbatim gate,
`claude -p` pattern, prompt DNA) are preserved in `reference/` and mapped in
`PLAN.md`.

## Authors

- **Poe** — atmospheric flash pieces (the short-story seat)
- **Emerson** — essays (the essayist seat)
- **Nietzsche** — essays, via the PD Common/Zimmern translations
- **Whitman** — poems, stitched by *line*, the classical cento form

The bench of future authors (and the public-domain traps that gate them)
is in `PLAN.md`.

## Status

Phases 0–4 done: corpus, gate, stitcher, site. See `PLAN.md` for the phases
and acceptance criteria; Phase 5 (daily rotation, GitHub Pages) is next.

```sh
bin/fetch_corpus.sh          # download + index the corpora (once)
python3 pipeline/segment.py  # rebuild the sentence index
bin/generate.sh poe          # theme → stitched, gated text in texts/
bin/generate.sh emerson      # (theme defaults to the first unused one)
bin/serve.sh                 # build the site, serve on localhost:8080
```

The index leads with the latest piece; `/feed.xml` is an Atom feed of all
pieces. Set `SITE_URL` (e.g. `SITE_URL=https://example.org bin/serve.sh`)
before deploying so canonical/OpenGraph/feed URLs point at the real host —
unset, they fall back to localhost and the build warns.

## Deployment

Live at <https://chrdamico.github.io/cento/>. Every push to `main` rebuilds
`site/out/` from the committed `texts/` and republishes
(`.github/workflows/pages.yml`). Generation never runs in CI — new pieces
are generated locally with `bin/generate.sh` and pushed.

Zero marginal cost by design: Claude subscription (`claude -p`, no API key),
Project Gutenberg corpora fetched once, static site.
