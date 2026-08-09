      --disallowedTools "Bash Edit Write Read Glob Grep WebFetch WebSearch NotebookEdit Task" \
  ) < "$1" > "$2"
}

# --- verbatim gate ------------------------------------------------------------
# The stitching contract, enforced. The prompt asks the model to assemble posts
# out of the author's own sentences; this is the part that doesn't take its word
# for it. Every sentence of the candidate body is searched for in the corpus:
#
#   VERBATIM  found character-for-character in one of the notes
#   TWEAKED   found after trimming up to 3 words off either end (a seam trim);
#             what remains must still be >= 60% of the sentence
#   GLUE      not found, but short enough (<= GLUE_MAX_WORDS words) to be a
#             connective the prompt allows
#   NEW       not found and too long to be glue — the model wrote prose
#
# A candidate passes only if it has no NEW sentences and at most
# max(1, (100-VERBATIM_MIN)% of its sentences) GLUE ones. The per-sentence
# classification doubles as the provenance report.
#
# $1 = body file, $2 = corpus file (with "### NOTE id=" markers). The report
# goes to stdout; the exit status is the verdict.
verbatim_gate() {
  awk -v min_pct="$VERBATIM_MIN" -v glue_max="$GLUE_MAX_WORDS" '
    function norm(s) {
      gsub(/[\342\200\230\342\200\231]/, "\x27", s)   # curly apostrophes
      gsub(/[\342\200\234\342\200\235]/, "\"", s)     # curly double quotes
      gsub(/[[:space:]]+/, " ", s)
      sub(/^ +/, "", s); sub(/ +$/, "", s)
      return tolower(s)
    }
    # which note contains s verbatim? empty if none
    function source_of(s,   i) {
      for (i = 1; i <= nids; i++) if (index(ntext[ids[i]], s)) return ids[i]
      return ""
    }
    # seam trims: drop up to 3 words from either end; accept if what remains is
    # still most of the sentence and is verbatim somewhere
    function tweaked_source_of(s,   w, n, a, b, core, i, src) {
      n = split(s, w, " ")
      for (a = 0; a <= 3; a++) for (b = 0; b <= 3; b++) {
        if (a + b == 0 || n - a - b < 3) continue
        core = w[a + 1]
        for (i = a + 2; i <= n - b; i++) core = core " " w[i]
        if (length(core) >= 0.6 * length(s)) {
          src = source_of(core)
          if (src != "") return src
        }
      }
      return ""
    }
    NR == FNR {   # first file: the corpus, keyed by note id
      if ($0 ~ /^### NOTE id=/) { id = substr($0, 13); ids[++nids] = id; next }
      if (id != "") raw[id] = raw[id] " " $0
      next
    }
    FNR == 1 { for (i = 1; i <= nids; i++) ntext[ids[i]] = norm(raw[ids[i]]) }
    {         # second file: the candidate body, markdown decorations stripped
      line = $0
      sub(/^[[:space:]]*(#+|[-*>]|[0-9]+\.)[[:space:]]+/, "", line)
      body = body " " line
    }
    END {
      gsub(/[.!?][[:space:]]+/, "&\n", body)
      n = split(body, sents, "\n")
      for (i = 1; i <= n; i++) {
        s = norm(sents[i])
        if (length(s) < 16) continue    # too short to judge; free either way
        counted++
        d = sents[i]; gsub(/[[:space:]]+/, " ", d); sub(/^ /, "", d)
        src = source_of(s)
        if (src != "") {
          verbatim++; printf "- VERBATIM [%s] %s\n", src, d
        } else if ((src = tweaked_source_of(s)) != "") {
          tweaked++;  printf "- TWEAKED  [%s] %s\n", src, d
        } else if (split(s, wtmp, " ") <= glue_max) {
          glue++;     printf "- GLUE     %s\n", d
        } else {
          new_++;     printf "- NEW      %s\n", d
        }
      }
      allowed_glue = int(counted * (100 - min_pct) / 100)
      if (allowed_glue < 1) allowed_glue = 1
      pass = (counted > 0 && new_ == 0 && glue <= allowed_glue)
      printf "\ngate: %s — %d verbatim, %d tweaked, %d glue (max %d), %d new of %d sentences\n",
