#!/usr/bin/env python3
"""replay_harness.py — LOCAL-647 narration MODEL bake-off on identical inputs.

Michael 2026-10-09: "optimise the calls and try cheaper vendors, measured on
what we already have." The main narration call (generate_tour_text.py, the
per-stop "story pass") is ~64% of OpenAI spend at ~3 calls/stop with gpt-4.1.
This harness measures ONE draft per stop per model, on identical inputs, so the
only variable is the model.

WHAT IT DOES
------------
For a fixed list of stored museum stops (>=12 stops, >=4 museums incl. Courtauld,
Walters, Wallace and Frick), it rebuilds each stop's narration INPUT from SAVED
data only:
  * the venue_corpus pages_json (the same corpus text production injects), and
  * the venue_corpus story_elements_json (named people / dated episodes), and
  * the work's English Wikipedia extract, fetched for FREE from the Wikipedia
    REST/action API (NOT Serper, NOT a grounded Gemini call).
There is NO Gemini and NO Serper RESEARCH call anywhere in this harness — the
only paid calls are the narration drafts themselves (arms D/E call Gemini as the
WRITER, ungrounded, no tools).

It then builds the narration prompt by IMPORTING AND REUSING the production
prompt — generate_tour_text.build_museum_stop_prompt() — not a new one, and
appends the same facts-first / source-snippet / artist blocks the production
path appends. The model under test is chosen through the production env hook
generate_tour_text.narration_model_route() (NARRATION_PROVIDER/NARRATION_MODEL).

Every paid call is metered by the network meter (PYTHONPATH=/opt/meter) into the
paid_api_calls table, so $ per arm comes from the ledger, not an estimate.

USAGE (inside the generator container, which has the meter + keys + DB):
    python3 replay_harness.py run  --arm A --out /app/bench_out/A
    python3 replay_harness.py build-only            # dump inputs/prompts, no calls
    python3 replay_harness.py report --dir /app/bench_out   # aggregate

ARMS (one draft per stop, no retries):
    A: gpt-4.1 (today)            B: gpt-4.1-mini      C: gpt-4.1-nano
    D: gemini-2.5-flash-lite      E: gemini-2.5-flash  (both ungrounded)
"""
import json
import os
import re
import sys
import time

import requests

# Reuse the PRODUCTION prompt builder and the model-selection env hook.
# generate_tour_text imports heavy deps at module load; that is fine inside the
# container image where this runs. We only call two pure helpers from it.
try:
    from generate_tour_text import build_museum_stop_prompt, narration_model_route
except Exception as _e:  # pragma: no cover
    print(f"[harness] FATAL: cannot import production prompt builder: {_e}",
          file=sys.stderr)
    raise

# ─── the production narration system message (verbatim) ──────────────────────
SYSTEM_MESSAGE = ("You are a knowledgeable museum guide with expertise in art, "
                  "architecture, and history.")

# ─── arm definitions ─────────────────────────────────────────────────────────
ARMS = {
    "A": ("openai", "gpt-4.1"),
    "B": ("openai", "gpt-4.1-mini"),
    "C": ("openai", "gpt-4.1-nano"),
    "D": ("gemini", "gemini-2.5-flash-lite"),
    "E": ("gemini", "gemini-2.5-flash"),
}

# ─── the 12 stops: (museum label, venue_corpus qid, stop_pool venue_identity,
#      pool_version). Stops themselves are read live from stop_pool so the
#      titles/subjects are exactly what the pipeline stored. ───────────────────
STOP_SOURCES = [
    ("Courtauld", "Q12110695", "qid:Q12110695", 21),
    ("Walters",   "Q210081",   "qid:Q210081",   21),
    ("Wallace",   "Q1327919",  "qid:Q1327919",  14),
    ("Frick",     "Q682827",   "loc:frick collection new york usa", 11),
]

WIKI_UA = {"User-Agent": "Audioura-LOCAL647-bakeoff/1.0 (replay harness; contact ops)"}

# Free Wikipedia extracts are fetched ONCE and cached here so every arm runs on
# byte-for-byte identical inputs (and we never re-hammer the rate-limited API).
WIKI_CACHE = os.environ.get("WIKI_CACHE", "/app/bench_out/_wiki_cache")


# ─── DB ──────────────────────────────────────────────────────────────────────
def _conn():
    import psycopg2
    dburl = os.environ.get("DATABASE_URL")
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"))


def load_stops():
    """Load the 12 stops with their saved corpus pages + story elements.

    Returns a list of dicts:
      {stop_id, museum, qid, title, artist, year, pages:[{url,text,title}],
       story_elements:[...], venue_name}
    """
    con = _conn()
    cur = con.cursor()
    stops = []
    for museum, qid, venue_identity, pool_version in STOP_SOURCES:
        # corpus for this museum (pages + story elements) — one row per qid
        cur.execute(
            "SELECT venue_name, pages_json, story_elements_json "
            "FROM venue_corpus WHERE qid=%s ORDER BY created_at DESC LIMIT 1",
            (qid,))
        row = cur.fetchone()
        venue_name = row[0] if row else museum
        pages = row[1] if row and isinstance(row[1], list) else []
        story_elements = row[2] if row and isinstance(row[2], list) else []
        # the stops for this museum
        cur.execute(
            "SELECT order_seq, title, artist, year FROM stop_pool "
            "WHERE venue_identity=%s AND pool_version=%s ORDER BY order_seq",
            (venue_identity, pool_version))
        rows = cur.fetchall()
        for order_seq, title, artist, year in rows:
            stops.append({
                "stop_id": f"{museum}-{order_seq}",
                "museum": museum,
                "qid": qid,
                "venue_name": venue_name,
                "title": (title or "").strip(),
                "artist": (artist or "").strip(),
                "year": (year or "").strip(),
                "pages": pages,
                "story_elements": story_elements,
            })
    con.close()
    return stops


# ─── research rebuild (FREE sources only — no Serper, no Gemini research) ─────
def _clean_title(title):
    """Strip the pipeline's narrative prefixes to get a searchable work name."""
    t = title
    # remove possessive artist prefixes and editorialising adjectives the pool adds
    t = re.sub(r"^(Van Gogh[\u2019']s iconic|Manet[\u2019']s(?: groundbreaking"
               r"(?: depiction of modern life)?)?|C[eé]zanne[\u2019']s)\s+", "", t)
    t = re.sub(r"\s*\(\d{4}\)\s*$", "", t)  # trailing "(1872)"
    return t.strip()


def wikipedia_extract(title):
    """The work's English Wikipedia plain-text extract, fetched for FREE.

    Two action-API calls to en.wikipedia.org (search then extract). This is the
    free channel the LEAD prototype used; it is NOT Serper and NOT a grounded
    Gemini call, so it does not appear in paid_api_calls.

    Wikipedia rate-limits bursts (HTTP 429), so we throttle politely and retry
    with backoff. Results are cached on disk (WIKI_CACHE) so the extract is
    fetched ONCE and reused byte-for-byte across all five arms — this is what
    makes the arms run on *identical* inputs.
    """
    q = _clean_title(title)
    cache_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", q)[:120]
    cache_path = os.path.join(WIKI_CACHE, cache_key + ".json")
    if os.path.exists(cache_path):
        try:
            d = json.load(open(cache_path, encoding="utf-8"))
            return d.get("page_title", ""), d.get("extract", "")
        except Exception:
            pass

    def _get(params, tries=5):
        for attempt in range(tries):
            try:
                r = requests.get("https://en.wikipedia.org/w/api.php",
                                 params=params, timeout=30, headers=WIKI_UA)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    wait = 3 * (attempt + 1)
                    print(f"  [wiki] 429, backing off {wait}s ({q!r})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                return None
            except Exception as ex:
                print(f"  [wiki] error ({q!r}): {ex}", file=sys.stderr)
                time.sleep(2)
        return None

    page_title, extract = "", ""
    s = _get({"action": "query", "list": "search", "srsearch": q + " painting",
              "format": "json", "srlimit": 1})
    time.sleep(1.0)  # polite inter-request delay
    if s:
        hits = s.get("query", {}).get("search", [])
        if hits:
            page_title = hits[0]["title"]
            e = _get({"action": "query", "prop": "extracts", "explaintext": 1,
                      "titles": page_title, "format": "json"})
            time.sleep(1.0)
            if e:
                pages = e.get("query", {}).get("pages", {})
                extract = (list(pages.values())[0].get("extract", "")
                           if pages else "")[:6000]
    # cache (even empties, so a genuine miss isn't re-hammered)
    try:
        os.makedirs(WIKI_CACHE, exist_ok=True)
        json.dump({"query": q, "page_title": page_title, "extract": extract},
                  open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    return page_title, extract


def corpus_bits(title, pages, limit=3000):
    """Paragraphs from the saved venue_corpus pages that mention this work."""
    keys = re.findall(r"[A-Za-z\u00C0-\u017F]{5,}", _clean_title(title))[:3]
    out = []
    for p in (pages or []):
        txt = (p.get("text") if isinstance(p, dict) else str(p)) or ""
        for para in txt.split("\n"):
            para = para.strip()
            if len(para) > 80 and any(k.lower() in para.lower() for k in keys):
                out.append(para)
    # dedupe preserving order
    seen = set()
    uniq = []
    for para in out:
        if para not in seen:
            seen.add(para)
            uniq.append(para)
    return "\n".join(uniq)[:limit]


def relevant_story_elements(title, artist, story_elements, limit=6):
    """Story elements whose text/people/source mention this work or artist."""
    keys = [k.lower() for k in re.findall(r"[A-Za-z\u00C0-\u017F]{4,}", _clean_title(title))][:4]
    if artist:
        keys += [w.lower() for w in artist.split() if len(w) > 2]
    picked = []
    for se in (story_elements or []):
        if not isinstance(se, dict):
            continue
        hay = (se.get("text", "") + " " + se.get("source_sentence", "") + " "
               + " ".join(se.get("people", []) or [])).lower()
        if any(k in hay for k in keys):
            picked.append(se)
    # rank by provided rank_score desc when present
    picked.sort(key=lambda s: float(s.get("rank_score", 0) or 0), reverse=True)
    return picked[:limit]


def build_stop_input(stop):
    """Rebuild the narration INPUT (research text) for one stop from saved data.

    Returns a dict with the research string plus the structured pieces so the
    prompt-diet variant can cap/dedupe them independently.
    """
    wiki_title, wiki_extract = wikipedia_extract(stop["title"])
    cbits = corpus_bits(stop["title"], stop["pages"])
    ses = relevant_story_elements(stop["title"], stop["artist"], stop["story_elements"])
    se_lines = []
    for se in ses:
        src = se.get("source_sentence") or se.get("text") or ""
        if src:
            se_lines.append(src.strip())
    # candidate specifics = the story-element source sentences (concrete, sourced)
    specifics = se_lines[:]
    # required names = people named by the matched story elements
    names = []
    for se in ses:
        for person in (se.get("people", []) or []):
            if person and person not in names:
                names.append(person)
    research = (f"[Wikipedia: {wiki_title}]\n{wiki_extract}\n\n"
                f"[Venue sources]\n{cbits}\n\n"
                f"[Documented episodes]\n" + "\n".join(f"- {s}" for s in se_lines)).strip()
    return {
        "wiki_title": wiki_title,
        "wiki_extract": wiki_extract,
        "corpus_bits": cbits,
        "story_elements": ses,
        "specifics": specifics,
        "names": names,
        "research": research,
    }


# ─── prompt assembly: REUSE the production builder + production-shape blocks ──
def _facts_first_block(names, specifics, artist, diet=False):
    """Reproduce the production LOCAL-408/417 facts-first block from saved data."""
    parts = []
    verified_names = names[:4]
    if verified_names or artist:
        parts.append("\u2501\u2501\u2501 NAMES THAT MUST APPEAR (your text is rejected without these) \u2501\u2501\u2501")
        for n in verified_names:
            parts.append(f"  \u2022 {n.split()[-1]} ({n})")
        if artist:
            parts.append(f"  \u2022 {artist.split()[-1]} ({artist}, artist)")
        parts.append("\u2501\u2501\u2501 END REQUIRED NAMES \u2501\u2501\u2501")
        parts.append("")
    cap = 3 if diet else 6
    if specifics:
        parts.append("\u2501\u2501\u2501 CONCRETE FACTS TO USE (prefer these over general claims) \u2501\u2501\u2501")
        for s in specifics[:cap]:
            parts.append(f"  \u2022 {s}")
        parts.append("\u2501\u2501\u2501 END CONCRETE FACTS \u2501\u2501\u2501")
        parts.append("")
    return ("\n".join(parts) + "\n\n") if parts else ""


def _source_snippets_block(stop_input, diet=False):
    """The source material block (Wikipedia + venue corpus), capped like production."""
    wiki = stop_input["wiki_extract"]
    cbits = stop_input["corpus_bits"]
    wiki_cap = 1800 if diet else 4000
    corpus_cap = 1200 if diet else 3000
    block = "\nSOURCE MATERIAL (use ONLY these facts; do not invent names, dates or numbers):\n"
    if wiki:
        block += f"\n[Reference extract]\n{wiki[:wiki_cap]}\n"
    if cbits:
        block += f"\n[Venue sources]\n{cbits[:corpus_cap]}\n"
    return block


def build_prompt(stop, stop_input, diet=False, fixed_first=False):
    """Build the full narration USER message, reusing the production builder.

    diet=True       -> trimmed variant (dedupe instructions already deduped by
                       reuse; cap snippets; cap specifics).
    fixed_first=True -> put the FIXED production instruction body FIRST and the
                       per-stop variable material LAST, for OpenAI automatic
                       prompt caching (longest shared prefix wins).
    """
    base = build_museum_stop_prompt(
        stop["title"], stop["venue_name"], "museum",
        stop_context_line="", unconfirmed_line="", visited_line="", claims_line="",
        style_constraint_block_museum="", style_constraints_disabled=True,
    )
    facts = _facts_first_block(stop_input["names"], stop_input["specifics"],
                               stop["artist"], diet=diet)
    snippets = _source_snippets_block(stop_input, diet=diet)
    if fixed_first:
        # FIXED first (base instructions), VARIABLE last (facts + snippets).
        # The base still contains the stop title in its first line; for caching we
        # keep the big shared instruction body as the common prefix.
        return base + "\n" + facts + snippets
    # production order: facts-first prepended after the task line, then base, then snippets
    first_nl = base.find("\n")
    if facts and first_nl > 0:
        prompt = base[:first_nl + 1] + "\n" + facts + base[first_nl + 1:]
    else:
        prompt = facts + base
    return prompt + snippets


# ─── model calls (ONE draft, NO retries) ─────────────────────────────────────
def call_openai(model, system_msg, user_msg, timeout=120):
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0.7, "max_tokens": 1000,
              "messages": [{"role": "system", "content": system_msg},
                           {"role": "user", "content": user_msg}]},
        timeout=timeout)
    status = r.status_code
    j = r.json()
    text = ""
    usage = {}
    if status == 200:
        text = j["choices"][0]["message"]["content"]
        usage = j.get("usage", {}) or {}
    else:
        text = f"[HTTP {status}] {json.dumps(j)[:500]}"
    return text, usage, status


def call_gemini(model, system_msg, user_msg, timeout=120):
    """Ungrounded Gemini generateContent — NO tools, NO grounding."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    prompt = system_msg + "\n\n" + user_msg
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {
                  "temperature": 0.7,
                  "maxOutputTokens": 1400,
                  "thinkingConfig": {"thinkingBudget": 0},
              }},  # NO 'tools' key -> no google_search -> ungrounded
        timeout=timeout)
    status = r.status_code
    j = r.json()
    text = ""
    usage = {}
    if status == 200:
        try:
            parts = j["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            text = f"[gemini empty] {json.dumps(j)[:400]}"
        um = j.get("usageMetadata", {}) or {}
        usage = {"prompt_tokens": um.get("promptTokenCount", 0),
                 "completion_tokens": (um.get("candidatesTokenCount", 0)
                                       + um.get("thoughtsTokenCount", 0)),
                 "total_tokens": um.get("totalTokenCount", 0)}
    else:
        text = f"[HTTP {status}] {json.dumps(j)[:500]}"
    return text, usage, status


def run_arm(arm, out_dir, diet=False, fixed_first=False, stops=None, limit=None):
    provider, model = ARMS[arm]
    # drive the production env hook so the model under test is selected the
    # production way (and prove the default path is untouched when unset).
    os.environ["NARRATION_PROVIDER"] = provider
    os.environ["NARRATION_MODEL"] = model
    routed_provider, routed_model = narration_model_route()
    assert (routed_provider, routed_model) == (provider, model), \
        f"env hook mismatch: {(routed_provider, routed_model)} != {(provider, model)}"

    os.makedirs(out_dir, exist_ok=True)
    stops = stops if stops is not None else load_stops()
    if limit:
        stops = stops[:int(limit)]
    results = []
    for stop in stops:
        si = stop.setdefault("_input", build_stop_input(stop))
        prompt = build_prompt(stop, si, diet=diet, fixed_first=fixed_first)
        t0 = time.time()
        if provider == "openai":
            text, usage, status = call_openai(model, SYSTEM_MESSAGE, prompt)
        else:
            text, usage, status = call_gemini(model, SYSTEM_MESSAGE, prompt)
        elapsed = round(time.time() - t0, 2)
        rec = {
            "arm": arm, "provider": provider, "model": model,
            "stop_id": stop["stop_id"], "museum": stop["museum"],
            "title": stop["title"], "artist": stop["artist"],
            "prompt_chars": len(prompt), "status": status,
            "seconds": elapsed, "usage": usage,
            "output": text,
        }
        results.append(rec)
        # raw output file per stop
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stop["stop_id"])
        with open(os.path.join(out_dir, f"{safe}.txt"), "w", encoding="utf-8") as f:
            f.write(f"ARM {arm} | {provider}:{model} | {stop['museum']} | {stop['title']}\n")
            f.write(f"prompt_chars={len(prompt)} status={status} seconds={elapsed} usage={usage}\n")
            f.write("=" * 80 + "\n")
            f.write(text)
        print(f"[{arm}] {stop['stop_id']:16s} status={status} "
              f"{elapsed:5.1f}s out_tok={usage.get('completion_tokens','?')} "
              f"chars={len(text)}", flush=True)
    with open(os.path.join(out_dir, f"arm_{arm}_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[{arm}] wrote {len(results)} stop results -> {out_dir}", flush=True)
    return results


def build_only(out_dir, diet=False, fixed_first=False):
    """Dump the rebuilt inputs + prompts without making ANY paid call."""
    os.makedirs(out_dir, exist_ok=True)
    stops = load_stops()
    for stop in stops:
        si = build_stop_input(stop)
        prompt = build_prompt(stop, si, diet=diet, fixed_first=fixed_first)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stop["stop_id"])
        with open(os.path.join(out_dir, f"{safe}.prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[build-only] {stop['stop_id']:16s} prompt_chars={len(prompt)} "
              f"names={len(si['names'])} specifics={len(si['specifics'])} "
              f"wiki={'yes' if si['wiki_extract'] else 'no'}", flush=True)
    print(f"[build-only] {len(stops)} stops -> {out_dir}", flush=True)


def _main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]

    def opt(name, default=None):
        if name in args:
            return args[args.index(name) + 1]
        return default

    diet = "--diet" in args
    fixed_first = "--fixed-first" in args
    if cmd == "run":
        arm = opt("--arm", "A")
        out = opt("--out", f"/app/bench_out/{arm}")
        limit = opt("--limit", None)
        run_arm(arm, out, diet=diet, fixed_first=fixed_first, limit=limit)
    elif cmd == "run-all":
        base = opt("--out", "/app/bench_out")
        limit = opt("--limit", None)
        only = opt("--arms", "ABCDE")
        # load stops ONCE so every arm runs on byte-for-byte identical inputs
        stops = load_stops()
        for st in stops:
            st["_input"] = build_stop_input(st)
        for arm in only:
            if arm not in ARMS:
                continue
            run_arm(arm, os.path.join(base, arm), diet=diet,
                    fixed_first=fixed_first, stops=stops, limit=limit)
    elif cmd == "build-only":
        out = opt("--out", "/app/bench_out/_prompts")
        build_only(out, diet=diet, fixed_first=fixed_first)
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    _main()
