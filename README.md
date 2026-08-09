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

## v1

Two authors, two texts each, served locally:

- **Poe** — atmospheric flash pieces (the short-story seat)
- **Emerson** — essays (the essayist seat)

## Status

Phase 0 — skeleton and plan. See `PLAN.md` for the phases and acceptance
criteria.

```sh
# once Phases 1–4 land:
bin/fetch_corpus.sh          # download + index the corpora (once)
bin/generate.sh poe          # theme → stitched, gated text in texts/
bin/generate.sh emerson
bin/serve.sh                 # build the site, serve on localhost
```

Zero marginal cost by design: Claude subscription (`claude -p`, no API key),
Project Gutenberg corpora fetched once, static site.
