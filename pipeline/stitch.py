"""Phase 3b: the stitcher — the single place the LLM appears.

theme -> working set -> claude -p (tools denied) -> candidate -> gate.
On gate FAIL the rejected candidate plus the per-sentence gate report is fed
back into the next call as GATE FEEDBACK (blog-pipeline's trick, made an
in-run retry), up to ATTEMPTS times; then give up loudly. The model's output
is never trusted — only what the gate verifies lands in texts/.

The claude invocation copies blog-pipeline's claude_transform: subscription
auth (no API key), prompt AND input as ONE delimited stdin stream (a -p
argument plus piped input is ambiguous and sometimes drops the input), all
FS/exec tools denied, run from work/ so a hallucinated tool call could not
touch the repo anyway.

CLI: python3 stitch.py --author poe [--theme "..."] [--out texts/...]
     theme defaults to the first authors.yaml theme without a text in texts/.
     exit 0 = a gated text was written; anything else failed loudly.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import authors as authors_mod
from gate import load_index, run_gate, report
from segment import slugify
from textsplit import split_sentences
from workingset import build

ROOT = authors_mod.ROOT
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")
TEXTS = os.path.join(ROOT, "texts")

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-fable-5")
ATTEMPTS = int(os.environ.get("ATTEMPTS", "3"))

# Same denial list as blog-pipeline's claude_transform — one string on purpose.
DISALLOWED = "Bash Edit Write Read Glob Grep WebFetch WebSearch NotebookEdit Task"

TEXT_BLOCK = re.compile(r"===== TEXT =====\s*\n(.*?)\n\s*===== END TEXT =====",
                        re.S)


def compose(prompt_text, theme, author_name, corpus, feedback):
    return "\n".join([
        prompt_text,
        "",
        f"THEME: {theme}",
        f"AUTHOR: {author_name}",
        "",
        "BEGIN CORPUS",
        corpus,
        "END CORPUS",
        "",
        "BEGIN GATE FEEDBACK",
        feedback,
        "END GATE FEEDBACK",
        "",
    ])


def call_claude(stream):
    os.makedirs(WORK, exist_ok=True)
    p = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", CLAUDE_MODEL,
         "--output-format", "text", "--disallowedTools", DISALLOWED],
        input=stream, capture_output=True, text=True, cwd=WORK)
    if p.returncode != 0:
        raise RuntimeError(
            f"claude exited {p.returncode}: {p.stderr.strip()[:500]}")
    return p.stdout


def parse_candidate(out):
    """-> {'title','sources','body'}, None for an honest NO CANDIDATE,
    or ValueError for a format violation (retryable via feedback)."""
    m = TEXT_BLOCK.search(out)
    if m is None:
        if re.search(r"^\s*NO CANDIDATE\s*$", out, re.M):
            return None
        raise ValueError("no ===== TEXT ===== block in output")
    head, sep, body = m.group(1).partition("----- body -----")
    if not sep:
        raise ValueError("TEXT block has no ----- body ----- divider")
    title, sources = "", []
    for line in head.splitlines():
        if line.startswith("title:"):
            title = line[len("title:"):].strip()
        elif line.startswith("sources:"):
            sources = [s.strip() for s in line[len("sources:"):].split(",")
                       if s.strip()]
    if not title or not body.strip():
        raise ValueError("TEXT block missing title or body")
    return {"title": title, "sources": sources, "body": body.strip()}


def mark_para_breaks(body, sentences):
    """The gate flattens the body; recover the candidate's paragraph breaks
    for the site by re-splitting per paragraph. Only trusted when the counts
    agree exactly — otherwise the text renders as one paragraph."""
    counts = [len(split_sentences(p)) for p in re.split(r"\n\s*\n", body)
              if p.strip()]
    if sum(counts) != len(sentences):
        return
    i = 0
    for c in counts:
        if c:
            sentences[i]["pbreak"] = True
        i += c


def unused_theme(author, meta):
    used = set()
    adir = os.path.join(TEXTS, author)
    if os.path.isdir(adir):
        for fn in os.listdir(adir):
            if fn.endswith(".json"):
                with open(os.path.join(adir, fn), encoding="utf-8") as f:
                    used.add(json.load(f).get("theme"))
    for theme in meta["themes"]:
        if theme not in used:
            return theme
    raise SystemExit(f"{author}: every theme in authors.yaml already has a "
                     f"text; pass --theme explicitly")


def log_usage(step, in_chars, out_chars):
    os.makedirs(LOGS, exist_ok=True)
    ts = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(os.path.join(LOGS, "usage.tsv"), "a", encoding="utf-8") as f:
        f.write(f"{ts}\t{step}\t{CLAUDE_MODEL}\t{in_chars}\t{out_chars}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True)
    ap.add_argument("--theme")
    ap.add_argument("--out", help="output JSON path (default: texts/<author>/"
                                  "<slug>.json, deduped)")
    args = ap.parse_args()

    meta = authors_mod.load()[args.author]
    kind = meta["kind"]
    theme = args.theme or unused_theme(args.author, meta)
    prompt_path = os.path.join(ROOT, "prompts", f"stitch-{kind}.md")
    prompt_text = open(prompt_path, encoding="utf-8").read()

    print(f"stitch: {args.author} ({kind}) — theme: {theme}")
    corpus = build(args.author, theme, kind)
    index = load_index(args.author)

    os.makedirs(LOGS, exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    feedback = ""
    for attempt in range(1, ATTEMPTS + 1):
        print(f"stitch: attempt {attempt}/{ATTEMPTS} "
              f"({CLAUDE_MODEL}, this takes a while)...")
        stream = compose(prompt_text, theme, meta["name"], corpus, feedback)
        out = call_claude(stream)
        log_usage(f"stitch:{args.author}:a{attempt}", len(stream), len(out))
        raw_log = os.path.join(LOGS, f"stitch-{args.author}-{run_id}-a{attempt}.txt")
        with open(raw_log, "w", encoding="utf-8") as f:
            f.write(out)

        try:
            cand = parse_candidate(out)
        except ValueError as e:
            print(f"stitch: attempt {attempt} malformed: {e}")
            feedback = (f"Your previous output was rejected before checking: "
                        f"{e}. Emit exactly the required block and nothing "
                        f"else.\n\n{out.strip()[:2000]}")
            continue
        if cand is None:
            # An honest refusal; the corpus won't change between attempts,
            # so retrying is pointless.
            raise SystemExit(f"stitch: model declared NO CANDIDATE for "
                             f"'{theme}' — try another theme")

        result = run_gate(cand["body"], index, kind)
        print(report(result))
        if result["pass"]:
            mark_para_breaks(cand["body"], result["sentences"])
            record = {
                "author": args.author,
                "author_name": meta["name"],
                "kind": kind,
                "title": cand["title"],
                "theme": theme,
                "created": datetime.date.today().isoformat(),
                "gate": result["counts"],
                "works": result["works"],
                "sentences": result["sentences"],
            }
            out_path = args.out
            if not out_path:
                adir = os.path.join(TEXTS, args.author)
                os.makedirs(adir, exist_ok=True)
                base = os.path.join(adir, slugify(cand["title"]))
                out_path, n = base + ".json", 2
                while os.path.exists(out_path):
                    out_path, n = f"{base}-{n}.json", n + 1
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=1)
            print(f"stitch: PASS — {out_path}")
            return

        feedback = (f"title: {cand['title']}\n\n{cand['body']}\n\n"
                    f"--- verbatim checker verdicts ---\n{report(result)}")

    raise SystemExit(f"stitch: gave up after {ATTEMPTS} attempts — last raw "
                     f"output and gate reports are in {LOGS}/")


if __name__ == "__main__":
    main()
