"""Phase 2 acceptance tests for the gate (PLAN.md), run against the real
Poe index. No LLM involved — the material is stitched by hand from the index
itself, which is exactly the situation the gate must judge.

    python3 pipeline/test_gate.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate import load_index, run_gate

FAILURES = []


def check(name, cond, detail=""):
    status = "ok  " if cond else "FAIL"
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def pick(index, para_prefix, lo=40):
    """Sentences of one work, in index order, reasonably long."""
    out = []
    for p in index.paras.values():
        for r in p["records"]:
            if r["id"].startswith(para_prefix) and len(r["norm"]) >= lo:
                out.append(r)
    return out


def main():
    t0 = time.time()
    index = load_index("poe")
    load_s = time.time() - t0

    usher = pick(index, "poe/the-fall-of-the-house-of-usher/")
    ligeia = pick(index, "poe/ligeia/")
    masque = pick(index, "poe/the-masque-of-the-red-death/")
    assert len(usher) > 8 and len(ligeia) > 4 and len(masque) > 4

    # 1. hand-stitched paragraph of real sentences, three works, no long runs
    stitched = [usher[0], ligeia[0], masque[0], usher[3], ligeia[2], masque[2]]
    body = " ".join(r["text"] for r in stitched)
    t0 = time.time()
    res = run_gate(body, index, kind="story")
    gate_s = time.time() - t0
    check("stitched paragraph passes", res["pass"], "; ".join(res["reasons"]))
    got = [e.get("src") for e in res["sentences"] if e["class"] != "FREE"]
    want = [r["id"] for r in stitched]
    check("locators are exact", got == want, f"{got} != {want}")

    # 2. one sentence lightly paraphrased -> NEW -> fail
    words = stitched[3]["text"].split()
    words[len(words) // 2] = "somewhat"     # change one interior word
    paraphrased = list(stitched)
    body2 = " ".join(r["text"] for r in paraphrased[:3]) + " " + \
        " ".join(words) + " " + \
        " ".join(r["text"] for r in paraphrased[4:])
    res2 = run_gate(body2, index, kind="story")
    check("paraphrase fails", not res2["pass"])
    check("paraphrase classified NEW", res2["counts"]["NEW"] == 1,
          str(res2["counts"]))

    # 3. contiguous excerpt of one paragraph -> excerpt guard
    para = next(p for p in index.paras.values()
                if p["records"][0]["id"].startswith("poe/the-gold-bug/")
                and len(p["records"]) >= 6)
    body3 = " ".join(r["text"] for r in para["records"][:6])
    res3 = run_gate(body3, index, kind="story")
    check("excerpt fails", not res3["pass"])
    check("excerpt guard fired",
          any("excerpt guard" in r for r in res3["reasons"]),
          "; ".join(res3["reasons"]))

    # 4a. seam trim: 3 words dropped from the front (and recapitalized, as a
    # model producing readable prose would) -> still found by substring
    # search -> VERBATIM, never NEW. Locator must point at the victim.
    victim = usher[5]
    tw_words = victim["text"].split()[3:]
    tw_words[0] = tw_words[0].capitalize()
    body4 = " ".join([usher[0]["text"], ligeia[0]["text"], masque[0]["text"],
                      " ".join(tw_words), ligeia[2]["text"], masque[2]["text"]])
    res4 = run_gate(body4, index, kind="story")
    e4 = [e for e in res4["sentences"] if e["class"] != "FREE"][3]
    check("front-trimmed sentence is VERBATIM, gate passes",
          res4["pass"] and e4["class"] == "VERBATIM"
          and e4["src"] == victim["id"],
          f"pass={res4['pass']} class={e4['class']} src={e4.get('src')}")

    # 4b. micro-glue welded to a sentence edge ("And yet, <sentence>") ->
    # trimming the candidate finds the core -> TWEAKED, not NEW
    body4b = " ".join([usher[0]["text"], ligeia[0]["text"], masque[0]["text"],
                       "And yet, " + ligeia[2]["text"], masque[2]["text"]])
    res4b = run_gate(body4b, index, kind="story")
    tw = [e for e in res4b["sentences"] if e["class"] == "TWEAKED"]
    check("edge-welded sentence is TWEAKED, gate passes",
          res4b["pass"] and len(tw) == 1 and tw[0]["src"] == ligeia[2]["id"],
          f"pass={res4b['pass']} counts={res4b['counts']}")

    # 5. glue budget: one short standalone connective sentence is allowed
    body5 = " ".join([usher[0]["text"], "And what of the hour that followed?",
                      ligeia[0]["text"], masque[0]["text"], usher[3]["text"]])
    res5 = run_gate(body5, index, kind="story")
    check("single glue passes", res5["pass"] and res5["counts"]["GLUE"] == 1,
          f"pass={res5['pass']} counts={res5['counts']}")

    # 6. a NEW sentence dressed as long glue is still NEW
    body6 = " ".join([usher[0]["text"],
                      "the house waited for me as houses wait for the dead, "
                      "patient and hungry and full of remembering,",
                      ligeia[0]["text"], masque[0]["text"]])
    res6 = run_gate(body6, index, kind="story")
    check("long invented connective is NEW", res6["counts"]["NEW"] == 1
          and not res6["pass"], str(res6["counts"]))

    print(f"\nindex load {load_s:.2f}s, one gate run {gate_s:.2f}s")
    check("gate is fast enough", load_s + gate_s < 5.0)

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
        sys.exit(1)
    print("\nall gate acceptance tests pass")


if __name__ == "__main__":
    main()
