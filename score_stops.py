#!/usr/bin/env python3
"""score_stops.py — LOCAL-647 per-stop scoring (Kiro + deterministic detectors).

Scores every bake-off output stop two ways, mirroring the production QA tools but
adapted to a SINGLE stop of narration (no tour structure around it):

1) DETERMINISTIC DETECTORS (stop_detectors) — the subset of
   ~/Audioura/.continuous_dev/bench/detectors.py that applies to one stop's
   spoken text. The tour-structure checks (stop_count, directions, venue-as-stop,
   restaurant-last, cross-stop callbacks) are dropped because a single isolated
   stop has no such structure; the content-hygiene checks are kept.

2) KIRO CRITIQUE — the ~/Audioura/.continuous_dev/calib/critique.sh rubric,
   rewritten to "judge this single stop", run via `kiro-cli chat --no-interactive`.
   Produces a /10 score plus a defect table. We parse the leading score.

usage:
  python3 score_stops.py detectors --dir bench_out            # fast, offline
  python3 score_stops.py kiro --dir bench_out [--arms ABCDE]  # calls kiro-cli
  python3 score_stops.py all --dir bench_out
"""
import json
import os
import re
import subprocess
import sys

ARMS = ["A", "B", "C", "D", "E"]
KIRO = os.environ.get("KIRO_CLI", "kiro-cli")


# ─── deterministic per-stop detectors ────────────────────────────────────────
def stop_detectors(text):
    """Return a list of (name, detail) failures for ONE stop's narration text."""
    lines = text.split("\n")
    body = []
    skip = True
    for ln in lines:
        if skip and (ln.startswith("ARM ") or ln.startswith("prompt_chars=")
                     or set(ln.strip()) == {"="}):
            continue
        skip = False
        body.append(ln)
    spoken = "\n".join(body).strip()
    spoken = re.sub(r"(?mi)^\s*(Orientation|Description|Narration)\s*:\s*", "", spoken)

    fails = []

    def chk(name, cond, detail=""):
        if cond:
            fails.append((name, str(detail)[:160]))

    chk("markers", "<!--" in spoken or "-->" in spoken)
    chk("truncated_snippet",
        bool(re.search(r"\w\.\.\.(\s|$)|\u2026\s|\b(of|the|and|on|to|a)\.\s", spoken)))
    chk("stock_recency", bool(re.search(r"(?i)a moment ago|just now|you just saw", spoken)))
    chk("one_word_sentence",
        bool(re.search(r"(?m)(?<=[.!?] )[A-Z][a-z]+\.(?= [A-Z])", spoken)))
    chk("dangling_opener",
        any(re.match(r"(?i)(as a result|this (move|detail|decision)|that (move|decision))\b",
                     p.strip())
            for p in spoken.split("\n\n")
            if p.strip() and not re.match(r"(Stop|Orientation|Directions)", p.strip())))
    chk("recruitment_copy",
        bool(re.search(r"(?i)you'?ll learn|forge a career|study (in|with)|"
                       r"restaurants, bars and caf", spoken)))
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", spoken) if len(s.strip()) > 40]
    dups = {s for s in sents if sents.count(s) > 1}
    chk("duplicate_sentence", bool(dups), list(dups)[:1])
    chk("raw_label_dup",
        bool(re.search(r"(?i)\bopen open\b|admission is (single|standard) ticket", spoken)))
    chk("label_echo",
        bool(re.search(r"(?i)\badmission is (general|adult|regular|standard|single)\b|"
                       r"\bis open (sunday|monday|tuesday|wednesday|thursday|friday|saturday),",
                       spoken)))
    money = re.findall(r"[\u00a3\u20ac$]\s?\d+", spoken)
    chk("price_list_dump", len(money) > 2, f"{len(money)} prices spoken")
    hours = re.findall(r"(?i)\b(?:is open|open daily|open (?:mon|tue|wed|thu|fri|sat|sun)\w*|"
                       r"opening hours)\b", spoken)
    chk("hours_said_twice", len(hours) > 1, f"{len(hours)} hours statements")
    adm = re.findall(r"(?i)admission[^.]*\.", spoken)
    chk("admission_twice", len(adm) > 1)
    long_pf = [x for x in re.split(r"(?<=[.!?])\s+|\n+", spoken)
               if re.search(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(?:am|pm|AM|PM)\b", x)
               and len(x.split()) > 30]
    chk("long_practical_sentence", bool(long_pf))
    chk("dropped_word",
        bool(re.search(r"\b(of|the|at|in|to) (was|were|is|has)\b", spoken)))
    chk("empty_title_quotes", bool(re.search(r'"\s+"|\u201c\s*\u201d', spoken)))
    chk("lowercase_sentence_join",
        bool(re.search(r"\b[a-z]{3,} (During|After|Before|In|The|This|When)\s+[a-z]", spoken)))
    chk("http_error", spoken.startswith("[HTTP ") or spoken.startswith("[gemini empty]"))
    chk("rhetorical_question_end", spoken.rstrip().endswith("?"))
    chk("llm_refusal",
        bool(re.search(r"(?i)\b(I'?m sorry|I cannot|I can'?t|as an AI|I'?m unable)\b",
                       spoken[:400])))
    return fails


# ─── Kiro single-stop critique ───────────────────────────────────────────────
SINGLE_STOP_RUBRIC = """You are a demanding audio-tour editor reviewing a SINGLE museum stop of narration in the file {path} (read it). It is the exact text the voice speaks for ONE stop of a museum audio tour of {museum}; the artwork is "{title}". There is deliberately no surrounding tour structure — judge only this one stop, as a LISTENER standing in front of the work, using the owner's criteria:
1) the stop LEADS with the WORK and ARTIST (what it shows, how it was made and why that matters, meaning, what critics said, the artist's life at that moment) with emotional content; a genuine collector/provenance story (named people, motive, consequence) is a welcome minority element, but dry institutional filler (accession dates, budgets, renovations) is a defect;
2) every concept/person named in passing gets at least a clause of explanation (EXPLAIN-WHAT-YOU-NAME);
3) at least one sentence names a PHYSICAL property of the object (medium, material, technique, size, condition) tied to the story;
4) no unsupported praise ("a testament to genius") without the specific evidence that earns it;
5) audio hygiene: no rhetorical-question ending, no lists longer than three, no preaching/instructing the listener ("take a moment to", "imagine", "reflect");
6) factual red flags: claims that sound invented, OR a claim that this work hangs in a DIFFERENT museum than {museum} (use your own knowledge of where famous works actually hang), OR invented names/dates/prices.
Output ONLY markdown: FIRST line exactly "SCORE: N/10" (N may be a decimal), then a short table of defects (quote <=20 words, criterion, severity). Do not modify any file."""


def run_kiro_critique(path, museum, title, timeout=300):
    """Run kiro-cli on one stop file; return (score_float_or_None, raw_markdown)."""
    prompt = SINGLE_STOP_RUBRIC.format(path=path, museum=museum, title=title)
    try:
        proc = subprocess.run(
            [KIRO, "chat", "--no-interactive", "--trust-tools=fs_read", prompt],
            capture_output=True, text=True, timeout=timeout)
        out = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return None, "[kiro timeout]"
    except Exception as e:
        return None, f"[kiro error] {e}"
    m = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10", out, re.I)
    if not m:
        m = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*/\s*10\b", out)
    score = float(m.group(1)) if m else None
    return score, out


# ─── drivers ─────────────────────────────────────────────────────────────────
def _load_arm(d, arm):
    p = os.path.join(d, arm, f"arm_{arm}_results.json")
    return json.load(open(p, encoding="utf-8"))


def run_detectors(base_dir):
    out = {}
    for arm in ARMS:
        recs = _load_arm(base_dir, arm)
        arm_out = []
        for r in recs:
            fails = stop_detectors(r["output"])
            arm_out.append({"stop_id": r["stop_id"], "museum": r["museum"],
                            "title": r["title"], "status": r["status"],
                            "detector_failures": [f[0] for f in fails],
                            "detector_detail": fails,
                            "n_failures": len(fails)})
        out[arm] = arm_out
        tot = sum(a["n_failures"] for a in arm_out)
        print(f"[detectors] arm {arm}: {tot} total failures across {len(arm_out)} stops",
              flush=True)
    with open(os.path.join(base_dir, "detectors.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def run_kiro(base_dir, arms=None):
    arms = arms or ARMS
    crit_dir = os.path.join(base_dir, "_critiques")
    os.makedirs(crit_dir, exist_ok=True)
    out = {}
    # resume support: load any existing partial scores
    scores_path = os.path.join(base_dir, "kiro_scores.json")
    if os.path.exists(scores_path):
        try:
            out = json.load(open(scores_path, encoding="utf-8"))
        except Exception:
            out = {}
    for arm in arms:
        recs = _load_arm(base_dir, arm)
        done = {a["stop_id"]: a for a in out.get(arm, [])}
        arm_out = []
        for r in recs:
            if r["stop_id"] in done and done[r["stop_id"]].get("score") is not None:
                arm_out.append(done[r["stop_id"]])
                print(f"[kiro] {arm} {r['stop_id']:16s} score={done[r['stop_id']]['score']} (cached)",
                      flush=True)
                continue
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", r["stop_id"])
            stop_path = os.path.abspath(os.path.join(base_dir, arm, f"{safe}.txt"))
            score, raw = run_kiro_critique(stop_path, r["museum"], r["title"])
            with open(os.path.join(crit_dir, f"{arm}_{safe}.md"), "w",
                      encoding="utf-8") as f:
                f.write(raw)
            arm_out.append({"stop_id": r["stop_id"], "museum": r["museum"],
                            "title": r["title"], "score": score})
            print(f"[kiro] {arm} {r['stop_id']:16s} score={score}", flush=True)
            out[arm] = arm_out
            with open(scores_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        out[arm] = arm_out
        scores = [a["score"] for a in arm_out if a["score"] is not None]
        mean = round(sum(scores) / len(scores), 3) if scores else None
        print(f"[kiro] arm {arm}: mean={mean} (n={len(scores)})", flush=True)
        with open(scores_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def _main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    base = opt("--dir", "bench_out")
    arms = list(opt("--arms", "ABCDE"))
    if cmd == "detectors":
        run_detectors(base)
    elif cmd == "kiro":
        run_kiro(base, arms)
    elif cmd == "all":
        run_detectors(base)
        run_kiro(base, arms)
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    _main()
