#!/usr/bin/env python3
"""run_local875_live.py — LOCAL-875 live proof (budget $0.50, D753 discipline).

Three short tours, 3 stops each, in three different local languages:
  * "Longshan Temple and Ximending walk, Taipei"   -> zh-Hant
  * "Montmartre walk, Paris"                        -> fr
  * "Kitai-gorod walk, Moscow"                      -> ru

For each tour it PROVES the D768 behaviour against the REAL services:
  1. the local language is DETECTED (log) from the tour location;
  2. kind words are GENERATED ONCE per language via the real gpt-4.1-mini
     (metered), and a SECOND run makes NO generation call (DB + memo cache);
  3. each stop CLASSIFIES correctly (real Wikidata P31 lookup → classify_place);
  4. the local Wikipedia EDITION is fetched where it exists (real MediaWiki API);
  5. the added OpenAI cost is reported from the meter.

Discipline:
  * Writes ONLY a disposable DB (DATABASE_URL points at the throwaway
    `local875-db` container) — NEVER the shared development-postgres-2.
  * The network meter (sitecustomize) bills every paid call to service=LOCAL-875.
  * Wikidata / Wikipedia are free; the only paid calls are the gpt-4.1-mini kind
    word generations (≈ $0.001 each, once per new language).
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import local_language as L
import city_scope


# ── real Wikidata P31 lookup for a stop (free) ───────────────────────────────
_WD_API = "https://www.wikidata.org/w/api.php"
_UA = "Audioura/2.2 (LOCAL-875 live; support@audioura.com)"


def _get(url, params, timeout=15):
    qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def wikidata_p31(name, lang="en"):
    """Resolve a stop NAME to its first P31 Q-id (real Wikidata). '' on miss."""
    try:
        s = _get(_WD_API, {"action": "wbsearchentities", "search": name,
                           "language": lang if lang.startswith("zh") else lang[:2] or "en",
                           "uselang": "en", "type": "item", "limit": 3, "format": "json"})
        for hit in s.get("search", []):
            qid = hit.get("id", "")
            if not qid:
                continue
            e = _get(_WD_API, {"action": "wbgetentities", "ids": qid,
                               "props": "claims", "format": "json"})
            claims = (e.get("entities", {}).get(qid, {}) or {}).get("claims", {})
            for c in claims.get("P31", []):
                p31 = (c.get("mainsnak", {}).get("datavalue", {})
                       .get("value", {}).get("id", ""))
                if p31:
                    return p31, qid
    except Exception as ex:
        print(f"    wikidata lookup failed for {name!r}: {ex}")
    return "", ""


def wiki_label(name, lang):
    """The stop's Wikidata label in `lang` (local alias). '' on miss."""
    try:
        s = _get(_WD_API, {"action": "wbsearchentities", "search": name,
                           "language": "en", "type": "item", "limit": 1, "format": "json"})
        hits = s.get("search", [])
        if not hits:
            return ""
        qid = hits[0]["id"]
        e = _get(_WD_API, {"action": "wbgetentities", "ids": qid,
                           "props": "labels", "languages": lang, "format": "json"})
        return ((e.get("entities", {}).get(qid, {}).get("labels", {}) or {})
                .get(lang, {}) or {}).get("value", "")
    except Exception:
        return ""


TOURS = [
    ("Longshan Temple and Ximending walk, Taipei",
     ["Longshan Temple", "Ximending", "Bopiliao Historical Block"]),
    ("Montmartre walk, Paris",
     ["Sacré-Cœur", "Place du Tertre", "Moulin Rouge"]),
    ("Kitai-gorod walk, Moscow",
     ["Saint Basil's Cathedral", "Red Square", "GUM"]),
]


def meter_total():
    """Sum this task's metered OpenAI spend from the meter log."""
    log = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
    total = 0.0
    rows = 0
    by_service = {}
    if not os.path.exists(log):
        return 0.0, 0, {}
    with open(log) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            svc = r.get("service", "")
            cost = float(r.get("cost_usd", r.get("cost", 0)) or 0)
            by_service.setdefault(svc, 0.0)
            by_service[svc] += cost
            if svc == "LOCAL-875":
                total += cost
                rows += 1
    return total, rows, by_service


def run(second_run=False):
    tag = "RUN 2 (cache hit — no generation expected)" if second_run else "RUN 1"
    print(f"\n{'='*70}\n{tag}\n{'='*70}")
    llm_calls = {"n": 0}

    orig = L._default_llm

    def counting_llm(lang):
        llm_calls["n"] += 1
        print(f"    [generation] gpt-4.1-mini called for {lang!r}")
        return orig(lang)

    L._default_llm = counting_llm
    # drop the per-process memo between RUN 1 and RUN 2 so the DB cache alone
    # must suppress the second generation (the real-world "second tour" case).
    L._WORDS_MEMO.clear()

    seen_langs = []
    try:
        for scope, stops in TOURS:
            print(f"\n--- TOUR: {scope} ---")
            langs = L.languages_for(scope, use_cache=True)
            dominant = langs[0]
            cc = city_scope.requested_country(scope) or L._augmented_city_country(scope) or "?"
            print(f"  local language DETECTED: {langs}  (country={cc})")
            if dominant not in seen_langs:
                seen_langs.append(dominant)

            # kind words once per language (en/vi are fixtures; others generate)
            kw = L.kind_words(dominant, llm=counting_llm, use_cache=True)
            print(f"  kind_words({dominant}): {len(kw)} keys "
                  f"(sample temple={kw.get('temple')})")

            for stop in stops:
                p31, qid = wikidata_p31(stop, dominant)
                cls = L.classify_place(stop, wikidata_instance_of=p31)
                alias = wiki_label(stop, dominant)
                art = L.local_wikipedia_evidence(stop, dominant, use_cache=True)
                art_en = L.local_wikipedia_evidence(stop, "en", use_cache=True)
                print(f"    STOP {stop!r}: P31={p31 or '-'} -> "
                      f"{cls['group']}/{cls['subtype']} (conf {cls['confidence']}) | "
                      f"alias({dominant})={alias or '-'} | "
                      f"wiki[{dominant}]={'yes' if art else 'no'} wiki[en]="
                      f"{'yes' if art_en else 'no'}")
                time.sleep(0.3)  # be gentle on Wikidata
    finally:
        L._default_llm = orig
    print(f"\n  {tag}: generation calls = {llm_calls['n']} "
          f"(languages seen: {seen_langs})")
    return llm_calls["n"], seen_langs


def main():
    print("LOCAL-875 LIVE — budget $0.50, service=LOCAL-875, disposable DB only")
    print(f"DATABASE_URL={os.environ.get('DATABASE_URL','(unset)')}")
    print(f"PAID_API_LOG={os.environ.get('PAID_API_LOG','(unset)')}")

    n1, langs1 = run(second_run=False)
    n2, langs2 = run(second_run=True)

    total, rows, by_svc = meter_total()
    print(f"\n{'='*70}\nRESULT\n{'='*70}")
    print(f"RUN 1 generation calls: {n1}  (one per non-fixture language)")
    print(f"RUN 2 generation calls: {n2}  (MUST be 0 — cache hit)")
    print(f"metered OpenAI rows (service=LOCAL-875): {rows}")
    print(f"metered OpenAI spend (service=LOCAL-875): ${total:.4f}")
    print(f"all services in log: { {k: round(v,4) for k,v in by_svc.items()} }")
    ok = (n2 == 0)
    print(f"\nPASS (second run no generation): {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
